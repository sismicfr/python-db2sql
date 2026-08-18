"""MSSQL reader that collects database metadata via SQLAlchemy."""

from __future__ import annotations

from typing import Any, Iterator, List, Optional, Tuple

from sqlalchemy import create_engine, engine, text
from sqlalchemy.orm.session import Session, sessionmaker

from db2sql.application.ports import Logger
from db2sql.domain.model import Column, Database, Schema, Table
from db2sql.infrastructure.config import AppConfig
from db2sql.infrastructure.persistence import query_introspection
from db2sql.infrastructure.persistence.errors import SourceReaderError
from db2sql.infrastructure.persistence.foreign_keys import ForeignKeyColumn, attach_foreign_keys
from db2sql.infrastructure.url import build_url, redact_url


class MSSQLSourceReader:
    """MSSQL reader."""

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
        return build_url(self._config.server, "mssql+pymssql")

    def collect_metadata(self) -> Database:
        database = Database(str(self._config.server.dbname or ""))
        try:
            self._ensure_session()
            self._logger.info("reading schemas ...")
            self._read_schemas(database)
            self._logger.info("reading tables ...")
            self._read_tables(database)
            self._logger.info("reading columns ...")
            self._read_columns(database)
            self._logger.info("reading computed columns")
            self._read_computed_columns(database)
            self._logger.info("reading identity columns")
            self._read_identity_columns(database)
            self._logger.info("reading column constraints")
            self._read_column_constraints(database)
            self._logger.info("reading foreign keys")
            self._read_foreign_keys(database)
            self._logger.info("reading indexes")
            self._read_indexes(database)
        except Exception as exception:
            self._logger.error(str(exception))
            raise SourceReaderError("failed to collect database information") from exception
        return database

    def iter_rows(self, schema: str, table: Table, limit: int = -1) -> Iterator[Tuple[Any, ...]]:
        session = self._ensure_session()
        columns = ", ".join(f"[{name}]" for name in table.columns)
        top = f"TOP {limit} " if limit and limit > 0 else ""
        query = f"SELECT {top}{columns} FROM [{schema}].[{table.name}]"
        result: engine.Result[Any] = session.execute(text(query))
        for row in result:
            yield tuple(row)

    def describe_query(self, query: str) -> List[Column]:
        return query_introspection.describe_query(self._ensure_session(), query)

    def iter_query_rows(self, query: str, limit: int = -1) -> Iterator[Tuple[Any, ...]]:
        yield from query_introspection.iter_query_rows(self._ensure_session(), query, limit=limit)

    def _read_schemas(self, database: Database) -> None:
        try:
            r: engine.Result[Any] = self._ensure_session().execute(text("""
SELECT SCHEMA_NAME
FROM
    INFORMATION_SCHEMA.SCHEMATA s
WHERE EXISTS(
    SELECT 1
    FROM INFORMATION_SCHEMA.TABLES
    WHERE TABLE_SCHEMA = s.SCHEMA_NAME
)
ORDER BY
    SCHEMA_NAME
"""))
        except Exception as exc:
            raise SourceReaderError(f"Error connecting to database {exc}") from exc

        for row in r:
            database.add_schema(Schema(row.SCHEMA_NAME))

    def _read_tables(self, database: Database) -> None:
        r: engine.Result[Any] = self._ensure_session().execute(text("""
SELECT TABLE_SCHEMA, TABLE_NAME
FROM
    information_schema.tables
WHERE
    TABLE_TYPE = 'BASE TABLE'
    AND TABLE_NAME NOT IN ('dtproperties', 'sysdiagrams')
ORDER BY
    TABLE_SCHEMA, TABLE_NAME
"""))
        for row in r:
            database.add_table(row.TABLE_SCHEMA, Table(row.TABLE_NAME))

    def _read_columns(self, database: Database) -> None:
        r: engine.Result[Any] = self._ensure_session().execute(text("""
SELECT
    TABLE_SCHEMA,
    TABLE_NAME,
    COLUMN_NAME,
    COLUMN_DEFAULT,
    IS_NULLABLE,
    DATA_TYPE,
    CHARACTER_MAXIMUM_LENGTH,
    NUMERIC_PRECISION,
    NUMERIC_SCALE
FROM
    INFORMATION_SCHEMA.COLUMNS
ORDER BY
    TABLE_SCHEMA, TABLE_NAME, ORDINAL_POSITION
"""))

        for row in r:
            table = database.get_table(row.TABLE_SCHEMA, row.TABLE_NAME)
            if table:
                table.add_column(
                    Column(
                        name=row.COLUMN_NAME,
                        type=row.DATA_TYPE,
                        default=row.COLUMN_DEFAULT,
                        nullable=row.IS_NULLABLE == "YES",
                        char_length=row.CHARACTER_MAXIMUM_LENGTH or -1,
                        precision=row.NUMERIC_PRECISION,
                        scale=row.NUMERIC_SCALE,
                    )
                )

    def _read_computed_columns(self, database: Database) -> None:
        r: engine.Result[Any] = self._ensure_session().execute(text("""
SELECT S.NAME TABLE_SCHEMA, T.NAME TABLE_NAME, C.NAME COLUMN_NAME, C.DEFINITION
FROM SYS.COMPUTED_COLUMNS C
INNER JOIN SYS.TABLES T
  ON T.OBJECT_ID = C.OBJECT_ID
INNER JOIN SYS.SCHEMAS S
  ON S.SCHEMA_ID = T.SCHEMA_ID
        """))

        for row in r:
            table = database.get_table(row.TABLE_SCHEMA, row.TABLE_NAME)
            if table:
                column = table.get_column(row.COLUMN_NAME)
                if column:
                    column.computed_definition = row.DEFINITION

    def _read_identity_columns(self, database: Database) -> None:
        r: engine.Result[Any] = self._ensure_session().execute(text("""
SELECT s.name TABLE_SCHEMA,
    o.name TABLE_NAME,
    c.name COLUMN_NAME
FROM sys.identity_columns c
    INNER JOIN sys.objects o
        ON o.object_id = c.object_id
    INNER JOIN sys.schemas s
        ON o.schema_id = s.schema_id
WHERE s.name NOT IN ('sys')
ORDER BY 1, 2, 3
        """))

        for row in r:
            table = database.get_table(row.TABLE_SCHEMA, row.TABLE_NAME)
            if table:
                column = table.get_column(row.COLUMN_NAME)
                if column:
                    column.identity = True

    def _read_column_constraints(self, database: Database) -> None:
        r: engine.Result[Any] = self._ensure_session().execute(text("""
SELECT u.TABLE_SCHEMA, u.TABLE_NAME, u.COLUMN_NAME, c.CONSTRAINT_TYPE
FROM INFORMATION_SCHEMA.CONSTRAINT_COLUMN_USAGE u
INNER JOIN INFORMATION_SCHEMA.TABLE_CONSTRAINTS c
  ON  c.CONSTRAINT_NAME = u.CONSTRAINT_NAME
  AND c.CONSTRAINT_SCHEMA = u.CONSTRAINT_SCHEMA
WHERE c.CONSTRAINT_TYPE IN ('UNIQUE', 'PRIMARY KEY')
        """))

        for row in r:
            table = database.get_table(row.TABLE_SCHEMA, row.TABLE_NAME)
            if table:
                column = table.get_column(row.COLUMN_NAME)
                if column:
                    column.constraint = row.CONSTRAINT_TYPE

    def _read_foreign_keys(self, database: Database) -> None:
        r: engine.Result[Any] = self._ensure_session().execute(text("""
SELECT KCU1.CONSTRAINT_SCHEMA AS CONSTRAINT_SCHEMA,
  KCU1.CONSTRAINT_NAME AS CONSTRAINT_NAME,
  KCU1.TABLE_SCHEMA AS TABLE_SCHEMA,
  KCU1.TABLE_NAME AS TABLE_NAME,
  KCU1.COLUMN_NAME AS COLUMN_NAME,
  KCU1.ORDINAL_POSITION AS ORDINAL_POSITION,
  KCU2.CONSTRAINT_SCHEMA AS UNIQUE_CONSTRAINT_SCHEMA,
  KCU2.CONSTRAINT_NAME AS UNIQUE_CONSTRAINT_NAME,
  KCU2.TABLE_SCHEMA AS UNIQUE_TABLE_SCHEMA,
  KCU2.TABLE_NAME AS UNIQUE_TABLE_NAME,
  KCU2.COLUMN_NAME AS UNIQUE_COLUMN_NAME
FROM INFORMATION_SCHEMA.REFERENTIAL_CONSTRAINTS RC
JOIN INFORMATION_SCHEMA.KEY_COLUMN_USAGE KCU1
  ON  KCU1.CONSTRAINT_CATALOG = RC.CONSTRAINT_CATALOG
  AND KCU1.CONSTRAINT_SCHEMA = RC.CONSTRAINT_SCHEMA
  AND KCU1.CONSTRAINT_NAME = RC.CONSTRAINT_NAME
JOIN INFORMATION_SCHEMA.KEY_COLUMN_USAGE KCU2
  ON  KCU2.CONSTRAINT_CATALOG = RC.UNIQUE_CONSTRAINT_CATALOG
  AND KCU2.CONSTRAINT_SCHEMA = RC.UNIQUE_CONSTRAINT_SCHEMA
  AND KCU2.CONSTRAINT_NAME = RC.UNIQUE_CONSTRAINT_NAME
WHERE KCU1.ORDINAL_POSITION = KCU2.ORDINAL_POSITION
  AND KCU1.TABLE_SCHEMA not in ('sys', 'guest', 'information_schema')
ORDER BY CONSTRAINT_SCHEMA, CONSTRAINT_NAME, KCU1.ORDINAL_POSITION
        """))

        attach_foreign_keys(
            database,
            (
                ForeignKeyColumn(
                    constraint=row.CONSTRAINT_NAME,
                    schema=row.TABLE_SCHEMA,
                    table=row.TABLE_NAME,
                    column=row.COLUMN_NAME,
                    ref_schema=row.UNIQUE_TABLE_SCHEMA,
                    ref_table=row.UNIQUE_TABLE_NAME,
                    ref_column=row.UNIQUE_COLUMN_NAME,
                )
                for row in r
            ),
        )

    def _read_indexes(self, database: Database) -> None:
        r: engine.Result[Any] = self._ensure_session().execute(text("""
SELECT sch.name as TABLE_SCHEMA,
     t.name as TABLE_NAME,
     ind.name as INDEX_NAME,
     ind.index_id as INDEX_ID,
     ic.index_column_id as COLUMN_ID,
     col.name as COLUMN_NAME
FROM sys.indexes ind
INNER JOIN sys.index_columns ic
  ON  ind.object_id = ic.object_id
  AND ind.index_id = ic.index_id
INNER JOIN sys.columns col
  ON ic.object_id = col.object_id
  AND ic.column_id = col.column_id
INNER JOIN sys.tables t
  ON ind.object_id = t.object_id
INNER JOIN sys.schemas sch
  ON sch.schema_id = t.schema_id
WHERE ind.is_primary_key = 0
  AND ind.is_unique = 0
  AND ind.is_unique_constraint = 0
  AND t.is_ms_shipped = 0
  AND sch.name not in ('sys', 'guest', 'information_schema')
ORDER BY t.name, ind.name, ind.index_id, ic.index_column_id
        """))

        for row in r:
            table = database.get_table(row.TABLE_SCHEMA, row.TABLE_NAME)
            if table:
                table.add_index(row.INDEX_NAME, row.COLUMN_NAME)
