"""MySQL / MariaDB reader: collect metadata via INFORMATION_SCHEMA."""

from __future__ import annotations

from typing import Any, Dict, Iterator, List, Optional, Tuple
from urllib.parse import quote_plus

from sqlalchemy import create_engine, engine, text
from sqlalchemy.orm.session import Session, sessionmaker

from db2sql.application.ports import Logger
from db2sql.domain.model import (
    Column,
    Database,
    ForeignKey,
    ForeignKeyConstraint,
    Schema,
    Table,
)
from db2sql.infrastructure.config import AppConfig
from db2sql.infrastructure.persistence import query_introspection
from db2sql.infrastructure.persistence.errors import SourceReaderError


class MySQLSourceReader:
    """Collect metadata from a MySQL/MariaDB server."""

    def __init__(self, config: AppConfig, logger: Logger) -> None:
        self._config = config
        self._logger = logger
        self._engine: Optional[engine.base.Engine] = None
        self._session: Optional[Session] = None

    def _ensure_session(self) -> Session:
        if self._session is None:
            self._logger.info(f"set connection to {self._connection_string}")
            self._engine = create_engine(self._connection_string)
            self._session = sessionmaker(bind=self._engine)()
        return self._session

    @property
    def _connection_string(self) -> str:
        server = self._config.server
        port = f":{server.port}" if server.port else ""
        return "mysql+pymysql://{}:{}@{}{}/{}".format(
            quote_plus(server.username or ""),
            quote_plus(server.password or ""),
            server.hostname or "",
            port,
            server.dbname or "",
        )

    @property
    def _database_name(self) -> str:
        if not self._config.server.dbname:
            raise SourceReaderError("MySQL reader requires server.dbname")
        return str(self._config.server.dbname)

    def collect_metadata(self) -> Database:
        database = Database(self._database_name)
        try:
            self._ensure_session()
            database.add_schema(Schema(self._database_name))
            self._read_tables(database)
            self._read_columns(database)
            self._read_constraints(database)
            self._read_foreign_keys(database)
            self._read_indexes(database)
        except SourceReaderError:
            raise
        except Exception as exc:
            self._logger.error(str(exc))
            raise SourceReaderError("failed to collect database information") from exc
        return database

    def _read_tables(self, database: Database) -> None:
        rows = self._ensure_session().execute(
            text(
                "SELECT TABLE_NAME FROM INFORMATION_SCHEMA.TABLES "
                "WHERE TABLE_SCHEMA = :schema AND TABLE_TYPE = 'BASE TABLE' "
                "ORDER BY TABLE_NAME"
            ),
            {"schema": self._database_name},
        )
        for row in rows:
            database.add_table(self._database_name, Table(row.TABLE_NAME))

    def _read_columns(self, database: Database) -> None:
        rows = self._ensure_session().execute(
            text(
                "SELECT TABLE_NAME, COLUMN_NAME, COLUMN_DEFAULT, IS_NULLABLE, "
                "DATA_TYPE, CHARACTER_MAXIMUM_LENGTH, NUMERIC_PRECISION, "
                "NUMERIC_SCALE, EXTRA "
                "FROM INFORMATION_SCHEMA.COLUMNS "
                "WHERE TABLE_SCHEMA = :schema "
                "ORDER BY TABLE_NAME, ORDINAL_POSITION"
            ),
            {"schema": self._database_name},
        )
        for row in rows:
            table = database.get_table(self._database_name, row.TABLE_NAME)
            if table is None:
                continue
            column = Column(
                name=row.COLUMN_NAME,
                type=row.DATA_TYPE,
                default=row.COLUMN_DEFAULT,
                nullable=row.IS_NULLABLE == "YES",
                char_length=row.CHARACTER_MAXIMUM_LENGTH or -1,
                precision=row.NUMERIC_PRECISION,
                scale=row.NUMERIC_SCALE,
            )
            if row.EXTRA and "auto_increment" in row.EXTRA.lower():
                column.identity = True
            table.add_column(column)

    def _read_constraints(self, database: Database) -> None:
        rows = self._ensure_session().execute(
            text(
                "SELECT k.TABLE_NAME, k.COLUMN_NAME, t.CONSTRAINT_TYPE "
                "FROM INFORMATION_SCHEMA.KEY_COLUMN_USAGE k "
                "JOIN INFORMATION_SCHEMA.TABLE_CONSTRAINTS t "
                "  ON  t.CONSTRAINT_NAME = k.CONSTRAINT_NAME "
                "  AND t.TABLE_SCHEMA = k.TABLE_SCHEMA "
                "WHERE k.TABLE_SCHEMA = :schema "
                "  AND t.CONSTRAINT_TYPE IN ('PRIMARY KEY','UNIQUE')"
            ),
            {"schema": self._database_name},
        )
        for row in rows:
            table = database.get_table(self._database_name, row.TABLE_NAME)
            if table:
                column = table.get_column(row.COLUMN_NAME)
                if column:
                    column.constraint = row.CONSTRAINT_TYPE

    def _read_foreign_keys(self, database: Database) -> None:
        rows = self._ensure_session().execute(
            text(
                "SELECT CONSTRAINT_NAME, TABLE_NAME, COLUMN_NAME, "
                "REFERENCED_TABLE_NAME, REFERENCED_COLUMN_NAME "
                "FROM INFORMATION_SCHEMA.KEY_COLUMN_USAGE "
                "WHERE TABLE_SCHEMA = :schema AND REFERENCED_TABLE_NAME IS NOT NULL "
                "ORDER BY CONSTRAINT_NAME, ORDINAL_POSITION"
            ),
            {"schema": self._database_name},
        )

        groups: Dict[Tuple[str, str], List[Any]] = {}
        for row in rows:
            key = (row.TABLE_NAME, row.CONSTRAINT_NAME)
            groups.setdefault(key, []).append(row)

        for (table_name, constraint_name), fk_rows in groups.items():
            table = database.get_table(self._database_name, table_name)
            if table is None:
                continue
            cols: List[str] = []
            ref_cols: List[str] = []
            valid = True
            for row in fk_rows:
                column = table.get_column(row.COLUMN_NAME)
                if column is None:
                    valid = False
                    break
                column.foreign_key = ForeignKey(
                    self._database_name,
                    row.REFERENCED_TABLE_NAME,
                    row.REFERENCED_COLUMN_NAME,
                )
                cols.append(row.COLUMN_NAME)
                ref_cols.append(row.REFERENCED_COLUMN_NAME)
            if valid and cols:
                table.foreign_key_constraints.append(
                    ForeignKeyConstraint(
                        name=constraint_name,
                        ref_schema=self._database_name,
                        ref_table=fk_rows[0].REFERENCED_TABLE_NAME,
                        columns=tuple(cols),
                        ref_columns=tuple(ref_cols),
                    )
                )

    def _read_indexes(self, database: Database) -> None:
        rows = self._ensure_session().execute(
            text(
                "SELECT TABLE_NAME, INDEX_NAME, COLUMN_NAME "
                "FROM INFORMATION_SCHEMA.STATISTICS "
                "WHERE TABLE_SCHEMA = :schema AND NON_UNIQUE = 1 "
                "ORDER BY TABLE_NAME, INDEX_NAME, SEQ_IN_INDEX"
            ),
            {"schema": self._database_name},
        )
        for row in rows:
            table = database.get_table(self._database_name, row.TABLE_NAME)
            if table:
                table.add_index(row.INDEX_NAME, row.COLUMN_NAME)

    def iter_rows(self, schema: str, table: Table, limit: int = -1) -> Iterator[Tuple[Any, ...]]:
        session = self._ensure_session()
        columns = ", ".join(f"`{name}`" for name in table.columns)
        suffix = f" LIMIT {limit}" if limit and limit > 0 else ""
        query = f"SELECT {columns} FROM `{schema}`.`{table.name}`{suffix}"
        result: engine.Result[Any] = session.execute(text(query))
        for row in result:
            yield tuple(row)

    def describe_query(self, query: str) -> List[Column]:
        return query_introspection.describe_query(self._ensure_session(), query)

    def iter_query_rows(self, query: str, limit: int = -1) -> Iterator[Tuple[Any, ...]]:
        yield from query_introspection.iter_query_rows(self._ensure_session(), query, limit=limit)
