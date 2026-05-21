"""Oracle reader: collect metadata via ``ALL_*`` data-dictionary views."""

from __future__ import annotations

from typing import Any, Dict, Iterator, List, Optional, Tuple

from sqlalchemy import create_engine, engine, text
from sqlalchemy.orm.session import Session, sessionmaker

from db2sql.application.ports import Logger
from db2sql.domain.model import Column, Database, ForeignKey, Schema, Table
from db2sql.infrastructure.config import AppConfig
from db2sql.infrastructure.persistence import query_introspection
from db2sql.infrastructure.persistence.errors import SourceReaderError


def _normalize_oracle_type(raw: str) -> str:
    """Normalize Oracle data-type strings so the postgres emitter can map them.

    Oracle reports types like ``TIMESTAMP(6) WITH TIME ZONE`` or ``DATE``
    (which actually includes a time component). Strip precision parens and
    map ``DATE`` to ``timestamp`` so the emitter renders it as ``timestamp``
    in PostgreSQL.
    """
    if not raw:
        return raw
    upper = raw.upper()
    if upper == "DATE":
        return "timestamp"
    if upper.startswith("TIMESTAMP"):
        if "LOCAL TIME ZONE" in upper:
            return "timestamp with local time zone"
        if "WITH TIME ZONE" in upper:
            return "timestamp with time zone"
        return "timestamp"
    if "(" in upper:
        head, _, _ = upper.partition("(")
        return head.strip().lower()
    return upper.lower()


_SYSTEM_SCHEMAS = (
    "ANONYMOUS",
    "APEX_PUBLIC_USER",
    "APPQOSSYS",
    "AUDSYS",
    "CTXSYS",
    "DBSFWUSER",
    "DBSNMP",
    "DIP",
    "DVF",
    "DVSYS",
    "FLOWS_FILES",
    "GGSYS",
    "GSMADMIN_INTERNAL",
    "GSMCATUSER",
    "GSMUSER",
    "LBACSYS",
    "MDDATA",
    "MDSYS",
    "OJVMSYS",
    "OLAPSYS",
    "ORACLE_OCM",
    "ORDDATA",
    "ORDPLUGINS",
    "ORDSYS",
    "OUTLN",
    "REMOTE_SCHEDULER_AGENT",
    "SI_INFORMTN_SCHEMA",
    "SYS",
    "SYS$UMF",
    "SYSBACKUP",
    "SYSDG",
    "SYSKM",
    "SYSRAC",
    "SYSTEM",
    "WMSYS",
    "XDB",
    "XS$NULL",
)


class OracleSourceReader:
    """Collect metadata from an Oracle server."""

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
        options = server.options or {}
        driver = options.get("driver", "oracledb")
        port = f":{server.port}" if server.port else ""
        userinfo = "{}:{}".format(server.username or "", server.password or "")
        host = server.hostname or ""
        service_name = options.get("service_name")
        sid = options.get("sid")
        if service_name:
            return f"oracle+{driver}://{userinfo}@{host}{port}/?service_name={service_name}"
        target = sid or server.dbname or ""
        return f"oracle+{driver}://{userinfo}@{host}{port}/{target}"

    @property
    def _schema_filter(self) -> Optional[str]:
        """Optional single-schema filter taken from ``server.options['owner']``."""
        owner = (self._config.server.options or {}).get("owner")
        return owner.upper() if owner else None

    def _excluded_schemas_sql(self, alias: str) -> str:
        joined = ", ".join(f"'{name}'" for name in _SYSTEM_SCHEMAS)
        return f"{alias} NOT IN ({joined})"

    def collect_metadata(self) -> Database:
        database = Database(str(self._config.server.dbname or "oracle"))
        try:
            self._ensure_session()
            self._logger.info("reading schemas ...")
            self._read_schemas(database)
            self._logger.info("reading tables ...")
            self._read_tables(database)
            self._logger.info("reading columns ...")
            self._read_columns(database)
            self._logger.info("reading constraints ...")
            self._read_constraints(database)
            self._logger.info("reading foreign keys ...")
            self._read_foreign_keys(database)
            self._logger.info("reading indexes ...")
            self._read_indexes(database)
            self._logger.info("reading identity columns ...")
            self._read_identity_columns(database)
        except SourceReaderError:
            raise
        except Exception as exc:
            self._logger.error(str(exc))
            raise SourceReaderError("failed to collect database information") from exc
        return database

    def _read_schemas(self, database: Database) -> None:
        owner = self._schema_filter
        params: Dict[str, Any] = {}
        if owner:
            query = "SELECT DISTINCT OWNER FROM ALL_TABLES " "WHERE OWNER = :owner ORDER BY OWNER"
            params["owner"] = owner
        else:
            query = (
                "SELECT DISTINCT OWNER FROM ALL_TABLES "
                f"WHERE {self._excluded_schemas_sql('OWNER')} "
                "ORDER BY OWNER"
            )
        try:
            rows = self._ensure_session().execute(text(query), params)
        except Exception as exc:
            raise SourceReaderError(f"Error connecting to database {exc}") from exc
        for row in rows:
            database.add_schema(Schema(row.owner))

    def _read_tables(self, database: Database) -> None:
        owner = self._schema_filter
        params: Dict[str, Any] = {}
        clauses = ["t.IOT_NAME IS NULL"]
        if owner:
            clauses.append("t.OWNER = :owner")
            params["owner"] = owner
        else:
            clauses.append(self._excluded_schemas_sql("t.OWNER"))
        where = " AND ".join(clauses)
        rows = self._ensure_session().execute(
            text(
                "SELECT t.OWNER, t.TABLE_NAME "
                "FROM ALL_TABLES t "
                f"WHERE {where} "
                "ORDER BY t.OWNER, t.TABLE_NAME"
            ),
            params,
        )
        for row in rows:
            database.add_table(row.owner, Table(row.table_name))

    def _read_columns(self, database: Database) -> None:
        owner = self._schema_filter
        params: Dict[str, Any] = {}
        if owner:
            owner_clause = "c.OWNER = :owner"
            params["owner"] = owner
        else:
            owner_clause = self._excluded_schemas_sql("c.OWNER")
        rows = self._ensure_session().execute(
            text(
                "SELECT c.OWNER, c.TABLE_NAME, c.COLUMN_NAME, c.DATA_DEFAULT, "
                "       c.NULLABLE, c.DATA_TYPE, c.DATA_LENGTH, c.CHAR_LENGTH, "
                "       c.DATA_PRECISION, c.DATA_SCALE "
                "FROM ALL_TAB_COLUMNS c "
                f"WHERE {owner_clause} "
                "ORDER BY c.OWNER, c.TABLE_NAME, c.COLUMN_ID"
            ),
            params,
        )
        for row in rows:
            table = database.get_table(row.owner, row.table_name)
            if table is None:
                continue
            default = row.data_default
            if isinstance(default, str):
                default = default.strip().rstrip(";").strip() or None
            data_type = (row.data_type or "").lower()
            char_length = row.char_length if "char" in data_type else -1
            if not char_length:
                char_length = -1
            table.add_column(
                Column(
                    name=row.column_name,
                    type=_normalize_oracle_type(row.data_type),
                    default=default,
                    nullable=row.nullable == "Y",
                    char_length=char_length,
                    precision=row.data_precision,
                    scale=row.data_scale,
                )
            )

    def _read_constraints(self, database: Database) -> None:
        owner = self._schema_filter
        params: Dict[str, Any] = {}
        if owner:
            owner_clause = "c.OWNER = :owner"
            params["owner"] = owner
        else:
            owner_clause = self._excluded_schemas_sql("c.OWNER")
        rows = self._ensure_session().execute(
            text(
                "SELECT cc.OWNER, cc.TABLE_NAME, cc.COLUMN_NAME, "
                "       CASE c.CONSTRAINT_TYPE "
                "            WHEN 'P' THEN 'PRIMARY KEY' "
                "            WHEN 'U' THEN 'UNIQUE' "
                "       END AS CONSTRAINT_TYPE "
                "FROM ALL_CONSTRAINTS c "
                "JOIN ALL_CONS_COLUMNS cc "
                "  ON  cc.OWNER = c.OWNER "
                "  AND cc.CONSTRAINT_NAME = c.CONSTRAINT_NAME "
                f"WHERE {owner_clause} "
                "  AND c.CONSTRAINT_TYPE IN ('P', 'U')"
            ),
            params,
        )
        for row in rows:
            table = database.get_table(row.owner, row.table_name)
            if table is None:
                continue
            column = table.get_column(row.column_name)
            if column is not None:
                column.constraint = row.constraint_type

    def _read_foreign_keys(self, database: Database) -> None:
        owner = self._schema_filter
        params: Dict[str, Any] = {}
        if owner:
            owner_clause = "c.OWNER = :owner"
            params["owner"] = owner
        else:
            owner_clause = self._excluded_schemas_sql("c.OWNER")
        rows = self._ensure_session().execute(
            text(
                "SELECT cc.OWNER, cc.TABLE_NAME, cc.COLUMN_NAME, cc.POSITION, "
                "       rc.OWNER AS REF_OWNER, rc.TABLE_NAME AS REF_TABLE, "
                "       rc.COLUMN_NAME AS REF_COLUMN "
                "FROM ALL_CONSTRAINTS c "
                "JOIN ALL_CONS_COLUMNS cc "
                "  ON  cc.OWNER = c.OWNER "
                "  AND cc.CONSTRAINT_NAME = c.CONSTRAINT_NAME "
                "JOIN ALL_CONS_COLUMNS rc "
                "  ON  rc.OWNER = c.R_OWNER "
                "  AND rc.CONSTRAINT_NAME = c.R_CONSTRAINT_NAME "
                "  AND rc.POSITION = cc.POSITION "
                f"WHERE {owner_clause} "
                "  AND c.CONSTRAINT_TYPE = 'R' "
                "ORDER BY cc.OWNER, cc.TABLE_NAME, cc.CONSTRAINT_NAME, cc.POSITION"
            ),
            params,
        )
        for row in rows:
            table = database.get_table(row.owner, row.table_name)
            if table is None:
                continue
            column = table.get_column(row.column_name)
            if column is None:
                continue
            column.foreign_key = ForeignKey(row.ref_owner, row.ref_table, row.ref_column)

    def _read_indexes(self, database: Database) -> None:
        owner = self._schema_filter
        params: Dict[str, Any] = {}
        if owner:
            owner_clause = "i.TABLE_OWNER = :owner"
            params["owner"] = owner
        else:
            owner_clause = self._excluded_schemas_sql("i.TABLE_OWNER")
        rows = self._ensure_session().execute(
            text(
                "SELECT i.TABLE_OWNER, i.TABLE_NAME, i.INDEX_NAME, ic.COLUMN_NAME "
                "FROM ALL_INDEXES i "
                "JOIN ALL_IND_COLUMNS ic "
                "  ON  ic.INDEX_OWNER = i.OWNER "
                "  AND ic.INDEX_NAME = i.INDEX_NAME "
                f"WHERE {owner_clause} "
                "  AND i.UNIQUENESS = 'NONUNIQUE' "
                "  AND i.INDEX_TYPE NOT LIKE 'LOB%' "
                "ORDER BY i.TABLE_OWNER, i.TABLE_NAME, i.INDEX_NAME, ic.COLUMN_POSITION"
            ),
            params,
        )
        for row in rows:
            table = database.get_table(row.table_owner, row.table_name)
            if table is not None:
                table.add_index(row.index_name, row.column_name)

    def _read_identity_columns(self, database: Database) -> None:
        """Detect 12c+ identity columns. Silently skipped on older Oracle versions."""
        owner = self._schema_filter
        params: Dict[str, Any] = {}
        if owner:
            owner_clause = "OWNER = :owner"
            params["owner"] = owner
        else:
            owner_clause = self._excluded_schemas_sql("OWNER")
        try:
            rows = self._ensure_session().execute(
                text(
                    "SELECT OWNER, TABLE_NAME, COLUMN_NAME "
                    "FROM ALL_TAB_IDENTITY_COLS "
                    f"WHERE {owner_clause}"
                ),
                params,
            )
        except Exception:
            return
        for row in rows:
            table = database.get_table(row.owner, row.table_name)
            if table is None:
                continue
            column = table.get_column(row.column_name)
            if column is not None:
                column.identity = True

    def iter_rows(self, schema: str, table: Table, limit: int = -1) -> Iterator[Tuple[Any, ...]]:
        session = self._ensure_session()
        columns = ", ".join(f'"{name}"' for name in table.columns)
        query = f'SELECT {columns} FROM "{schema}"."{table.name}"'
        if limit and limit > 0:
            query += f" FETCH FIRST {limit} ROWS ONLY"
        result: engine.Result[Any] = session.execute(text(query))
        for row in result:
            yield tuple(row)

    def describe_query(self, query: str) -> List[Column]:
        return query_introspection.describe_query(self._ensure_session(), query)

    def iter_query_rows(self, query: str, limit: int = -1) -> Iterator[Tuple[Any, ...]]:
        yield from query_introspection.iter_query_rows(self._ensure_session(), query, limit=limit)
