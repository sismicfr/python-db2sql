"""PostgreSQL reader: collect metadata via INFORMATION_SCHEMA + pg_index."""

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

_SYSTEM_SCHEMAS = ("pg_catalog", "information_schema", "pg_toast")


class PostgresSourceReader:
    """Collect metadata from a PostgreSQL server."""

    def __init__(self, config: AppConfig, logger: Logger) -> None:
        self._config = config
        self._logger = logger
        self._engine: Optional[engine.base.Engine] = None
        self._session: Optional[Session] = None

    def _ensure_session(self) -> Session:
        if self._session is None:
            self._logger.info(f"set connection to {redact_url(self._connection_string)}")
            self._engine = create_engine(self._connection_string)
            self._session = sessionmaker(bind=self._engine)()
        return self._session

    @property
    def _connection_string(self) -> str:
        return build_url(self._config.server, "postgresql+psycopg2")

    def collect_metadata(self) -> Database:
        database = Database(str(self._config.server.dbname or ""))
        try:
            self._ensure_session()
            self._read_schemas_and_tables(database)
            self._read_columns(database)
            self._read_constraints(database)
            self._read_foreign_keys(database)
            self._read_indexes(database)
        except Exception as exc:
            self._logger.error(str(exc))
            raise SourceReaderError("failed to collect database information") from exc
        return database

    def _read_schemas_and_tables(self, database: Database) -> None:
        rows = self._ensure_session().execute(
            text(
                "SELECT TABLE_SCHEMA, TABLE_NAME "
                "FROM INFORMATION_SCHEMA.TABLES "
                "WHERE TABLE_TYPE = 'BASE TABLE' "
                f"  AND TABLE_SCHEMA NOT IN {_SYSTEM_SCHEMAS} "
                "ORDER BY TABLE_SCHEMA, TABLE_NAME"
            )
        )
        for row in rows:
            if row.table_schema not in database.schemas:
                database.add_schema(Schema(row.table_schema))
            database.add_table(row.table_schema, Table(row.table_name))

    def _read_columns(self, database: Database) -> None:
        rows = self._ensure_session().execute(
            text(
                "SELECT TABLE_SCHEMA, TABLE_NAME, COLUMN_NAME, COLUMN_DEFAULT, "
                "IS_NULLABLE, DATA_TYPE, CHARACTER_MAXIMUM_LENGTH, NUMERIC_PRECISION, "
                "NUMERIC_SCALE, IS_IDENTITY "
                "FROM INFORMATION_SCHEMA.COLUMNS "
                f"WHERE TABLE_SCHEMA NOT IN {_SYSTEM_SCHEMAS} "
                "ORDER BY TABLE_SCHEMA, TABLE_NAME, ORDINAL_POSITION"
            )
        )
        for row in rows:
            table = database.get_table(row.table_schema, row.table_name)
            if table is None:
                continue
            column = Column(
                name=row.column_name,
                type=row.data_type,
                default=row.column_default,
                nullable=row.is_nullable == "YES",
                char_length=row.character_maximum_length or -1,
                precision=row.numeric_precision,
                scale=row.numeric_scale,
            )
            if row.is_identity == "YES":
                column.identity = True
            table.add_column(column)

    def _read_constraints(self, database: Database) -> None:
        rows = self._ensure_session().execute(
            text(
                "SELECT k.TABLE_SCHEMA, k.TABLE_NAME, k.COLUMN_NAME, t.CONSTRAINT_TYPE "
                "FROM INFORMATION_SCHEMA.KEY_COLUMN_USAGE k "
                "JOIN INFORMATION_SCHEMA.TABLE_CONSTRAINTS t "
                "  ON  t.CONSTRAINT_NAME = k.CONSTRAINT_NAME "
                "  AND t.TABLE_SCHEMA = k.TABLE_SCHEMA "
                f"WHERE k.TABLE_SCHEMA NOT IN {_SYSTEM_SCHEMAS} "
                "  AND t.CONSTRAINT_TYPE IN ('PRIMARY KEY','UNIQUE')"
            )
        )
        for row in rows:
            table = database.get_table(row.table_schema, row.table_name)
            if table:
                column = table.get_column(row.column_name)
                if column:
                    column.constraint = row.constraint_type

    def _read_foreign_keys(self, database: Database) -> None:
        rows = self._ensure_session().execute(
            text(
                "SELECT k1.TABLE_SCHEMA, k1.TABLE_NAME, k1.COLUMN_NAME, "
                "       k1.CONSTRAINT_NAME, "
                "       k2.TABLE_SCHEMA AS REF_SCHEMA, k2.TABLE_NAME AS REF_TABLE, "
                "       k2.COLUMN_NAME AS REF_COLUMN "
                "FROM INFORMATION_SCHEMA.REFERENTIAL_CONSTRAINTS rc "
                "JOIN INFORMATION_SCHEMA.KEY_COLUMN_USAGE k1 "
                "  ON k1.CONSTRAINT_NAME = rc.CONSTRAINT_NAME "
                " AND k1.CONSTRAINT_SCHEMA = rc.CONSTRAINT_SCHEMA "
                "JOIN INFORMATION_SCHEMA.KEY_COLUMN_USAGE k2 "
                "  ON k2.CONSTRAINT_NAME = rc.UNIQUE_CONSTRAINT_NAME "
                " AND k2.CONSTRAINT_SCHEMA = rc.UNIQUE_CONSTRAINT_SCHEMA "
                " AND k1.ORDINAL_POSITION = k2.ORDINAL_POSITION "
                f"WHERE k1.TABLE_SCHEMA NOT IN {_SYSTEM_SCHEMAS} "
                "ORDER BY k1.TABLE_SCHEMA, k1.TABLE_NAME, k1.CONSTRAINT_NAME, "
                "         k1.ORDINAL_POSITION"
            )
        )
        attach_foreign_keys(
            database,
            (
                ForeignKeyColumn(
                    schema=row.table_schema,
                    table=row.table_name,
                    key=row.constraint_name,
                    column=row.column_name,
                    ref_schema=row.ref_schema,
                    ref_table=row.ref_table,
                    ref_column=row.ref_column,
                    name=row.constraint_name,
                )
                for row in rows
            ),
        )

    def _read_indexes(self, database: Database) -> None:
        rows = self._ensure_session().execute(
            text(
                "SELECT n.nspname AS schema_name, t.relname AS table_name, "
                "       i.relname AS index_name, a.attname AS column_name "
                "FROM pg_class t "
                "JOIN pg_index ix ON t.oid = ix.indrelid "
                "JOIN pg_class i ON i.oid = ix.indexrelid "
                "JOIN pg_namespace n ON n.oid = t.relnamespace "
                "JOIN pg_attribute a "
                "  ON a.attrelid = t.oid AND a.attnum = ANY(ix.indkey) "
                "WHERE t.relkind = 'r' AND NOT ix.indisunique AND NOT ix.indisprimary "
                f"  AND n.nspname NOT IN {_SYSTEM_SCHEMAS} "
                "ORDER BY schema_name, table_name, index_name"
            )
        )
        for row in rows:
            table = database.get_table(row.schema_name, row.table_name)
            if table:
                table.add_index(row.index_name, row.column_name)

    def iter_rows(self, schema: str, table: Table, limit: int = -1) -> Iterator[Tuple[Any, ...]]:
        session = self._ensure_session()
        columns = ", ".join(f'"{name}"' for name in table.columns)
        suffix = f" LIMIT {limit}" if limit and limit > 0 else ""
        query = f'SELECT {columns} FROM "{schema}"."{table.name}"{suffix}'
        result: engine.Result[Any] = session.execute(text(query))
        for row in result:
            yield tuple(row)

    def describe_query(self, query: str) -> List[Column]:
        return query_introspection.describe_query(self._ensure_session(), query)

    def iter_query_rows(self, query: str, limit: int = -1) -> Iterator[Tuple[Any, ...]]:
        yield from query_introspection.iter_query_rows(self._ensure_session(), query, limit=limit)
