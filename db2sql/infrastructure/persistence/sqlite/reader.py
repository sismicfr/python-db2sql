"""SQLite reader: collect metadata using ``PRAGMA`` queries via SQLAlchemy."""

from __future__ import annotations

from typing import Any, Dict, Iterator, List, Optional, Tuple

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
        path = self._config.server.options.get("path") or self._config.server.dbname
        if not path:
            raise SourceReaderError("SQLite reader requires server.dbname or options.path")
        return f"sqlite:///{path}"

    def _ensure_session(self) -> Session:
        if self._session is None:
            self._logger.info(f"set connection to {self._connection_string}")
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
        table = database.get_table(self._schema, table_name)
        if table is None:
            return

        # Group rows by constraint id (first element of each PRAGMA row)
        groups: Dict[int, List[Tuple[str, str, str]]] = {}
        for row in rows:
            fk_id, _, ref_table, src_col, ref_col, *_ = row
            groups.setdefault(fk_id, []).append((ref_table, src_col, ref_col))

        for fk_id, fk_rows in groups.items():
            cols: List[str] = []
            ref_cols: List[str] = []
            valid = True
            ref_table = fk_rows[0][0]
            for _, src_col, ref_col in fk_rows:
                column = table.get_column(src_col)
                if column is None:
                    valid = False
                    break
                column.foreign_key = ForeignKey(self._schema, ref_table, ref_col)
                cols.append(src_col)
                ref_cols.append(ref_col)
            if valid and cols:
                table.foreign_key_constraints.append(
                    ForeignKeyConstraint(
                        name=f"{table_name}_fk_{fk_id}",
                        ref_schema=self._schema,
                        ref_table=ref_table,
                        columns=tuple(cols),
                        ref_columns=tuple(ref_cols),
                    )
                )

    def iter_rows(self, schema: str, table: Table, limit: int = -1) -> Iterator[Tuple[Any, ...]]:
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
