"""SQLite reader: collect metadata using ``PRAGMA`` queries via SQLAlchemy."""

from __future__ import annotations

from typing import Any, Iterator, List, Optional, Tuple

from sqlalchemy import create_engine, engine, text
from sqlalchemy.orm.session import Session, sessionmaker

from db2sql.application.ports import Logger
from db2sql.domain.model import Column, Database, Schema, Table
from db2sql.infrastructure.config import AppConfig
from db2sql.infrastructure.persistence import query_introspection
from db2sql.infrastructure.persistence.errors import SourceReaderError
from db2sql.infrastructure.persistence.foreign_keys import (
    attach_foreign_keys,
    ForeignKeyColumn,
)
from db2sql.infrastructure.url import build_url, redact_url

_DEFAULT_SCHEMA = "public"


class SQLiteSourceReader:
    """Collect metadata from a SQLite file."""

    def __init__(self, config: AppConfig, logger: Logger) -> None:
        self._config = config
        self._logger = logger
        self._engine: Optional[engine.base.Engine] = None
        self._session: Optional[Session] = None
        self._schema = config.server.options.get("schema", _DEFAULT_SCHEMA)

    @property
    def _connection_string(self) -> str:
        server = self._config.server
        if server.dsn:
            return build_url(server, "sqlite", credentials=False)
        path = server.options.get("path") or server.dbname
        if not path:
            raise SourceReaderError("SQLite reader requires server.dbname, options.path, or a DSN")
        return build_url(server, "sqlite", database=str(path), credentials=False)

    def _ensure_session(self) -> Session:
        if self._session is None:
            self._logger.info(f"set connection to {redact_url(self._connection_string)}")
            self._engine = create_engine(self._connection_string)
            self._session = sessionmaker(bind=self._engine)()
        return self._session

    def collect_metadata(self) -> Database:
        database = Database(str(self._config.server.dbname or "sqlite"))
        try:
            session = self._ensure_session()
            database.add_schema(Schema(self._schema))
            tables = session.execute(
                text(
                    "SELECT name FROM sqlite_master "
                    "WHERE type='table' AND name NOT LIKE 'sqlite_%' "
                    "ORDER BY name"
                )
            ).fetchall()
            for (table_name,) in tables:
                database.add_table(self._schema, Table(table_name))
            for (table_name,) in tables:
                self._read_columns(database, table_name)
                self._read_indexes(database, table_name)
                self._read_foreign_keys(database, table_name)
        except SourceReaderError:
            raise
        except Exception as exception:
            self._logger.error(str(exception))
            raise SourceReaderError("failed to collect database information") from exception
        return database

    def _read_columns(self, database: Database, table_name: str) -> None:
        session = self._ensure_session()
        rows = session.execute(text(f'PRAGMA table_info("{table_name}")')).fetchall()
        table = database.get_table(self._schema, table_name)
        if table is None:
            return
        for row in rows:
            _, name, col_type, notnull, default, pk = row
            base_type = (col_type or "TEXT").lower()
            char_length = -1
            if "(" in base_type and base_type.endswith(")"):
                head, _, tail = base_type.partition("(")
                try:
                    char_length = int(tail[:-1].split(",")[0])
                except ValueError:
                    char_length = -1
                base_type = head
            is_autoincrement = pk == 1 and base_type in {"integer", "int"}
            column = Column(
                name=name,
                type=base_type,
                default=default,
                nullable=not bool(notnull),
                char_length=char_length,
            )
            if pk:
                column.constraint = "PRIMARY KEY"
            if is_autoincrement:
                column.identity = True
            table.add_column(column)

    def _read_indexes(self, database: Database, table_name: str) -> None:
        session = self._ensure_session()
        idx_rows = session.execute(text(f'PRAGMA index_list("{table_name}")')).fetchall()
        table = database.get_table(self._schema, table_name)
        if table is None:
            return
        for idx in idx_rows:
            _, idx_name, unique, origin, _ = idx
            if origin in {"pk", "u"} and unique:
                continue
            cols = session.execute(text(f'PRAGMA index_info("{idx_name}")')).fetchall()
            for col in cols:
                _, _, column_name = col
                table.add_index(idx_name, column_name)

    def _read_foreign_keys(self, database: Database, table_name: str) -> None:
        session = self._ensure_session()
        rows = session.execute(text(f'PRAGMA foreign_key_list("{table_name}")')).fetchall()
        # PRAGMA numbers each constraint in `id`; a composite key is several
        # rows sharing that id, `seq` giving the column order.
        attach_foreign_keys(
            database,
            (
                ForeignKeyColumn(
                    schema=self._schema,
                    table=table_name,
                    key=str(row[0]),
                    column=row[3],
                    ref_schema=self._schema,
                    ref_table=row[2],
                    ref_column=row[4],
                )
                for row in sorted(rows, key=lambda row: (row[0], row[1]))
            ),
        )

    def iter_rows(  # pylint: disable=unused-argument
        self, schema: str, table: Table, limit: int = -1
    ) -> Iterator[Tuple[Any, ...]]:
        session = self._ensure_session()
        columns = ", ".join(f'"{name}"' for name in table.columns)
        suffix = f" LIMIT {limit}" if limit and limit > 0 else ""
        result: engine.Result[Any] = session.execute(
            text(f'SELECT {columns} FROM "{table.name}"{suffix}')
        )
        for row in result:
            yield tuple(row)

    def describe_query(self, query: str) -> List[Column]:
        return query_introspection.describe_query(self._ensure_session(), query)

    def iter_query_rows(self, query: str, limit: int = -1) -> Iterator[Tuple[Any, ...]]:
        yield from query_introspection.iter_query_rows(self._ensure_session(), query, limit=limit)
