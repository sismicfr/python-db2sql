"""MSSQL writer: execute DDL via SQLAlchemy + batched ``executemany`` for bulk.

pymssql does not expose a ``fast_executemany`` flag (that's pyodbc-only). To
keep the writer dependency-light and aligned with the existing reader stack
(see ``infrastructure/persistence/mssql``), we batch rows in memory and call
``cursor.executemany`` on each batch. Throughput is fine for typical migration
workloads; switching to ``pyodbc + fast_executemany`` is a drop-in replacement
should the perf become a bottleneck.
"""

from __future__ import annotations

from types import TracebackType
from typing import Any, Iterator, List, Optional, Tuple

from sqlalchemy import create_engine, text
from sqlalchemy.engine import Connection, Engine

from db2sql.application.ports import Logger
from db2sql.domain.model import Table
from db2sql.domain.policy import normalize_identifier
from db2sql.infrastructure.config import AppConfig
from db2sql.infrastructure.url import build_url, redact_url
from db2sql.infrastructure.writer.errors import (
    TargetWriterConnectionError,
    TargetWriterExecutionError,
)


class MssqlTargetWriter:
    """Live-migrate target writer for Microsoft SQL Server."""

    _SESSION_STATEMENTS: Tuple[str, ...] = (
        "SET ANSI_NULLS ON",
        "SET QUOTED_IDENTIFIER ON",
        "SET DATEFORMAT ymd",
    )

    def __init__(self, config: AppConfig, logger: Logger) -> None:
        self._config = config
        self._logger = logger
        self._preserve_case: bool = config.dump.preserve_case
        self._engine: Optional[Engine] = None
        self._connection: Optional[Connection] = None
        self._batch_size = max(1, config.migrate.batch_size)

    # ---- lifecycle --------------------------------------------------------

    def __enter__(self) -> "MssqlTargetWriter":
        try:
            self._logger.info(f"connecting to target {self._connection_string_redacted}")
            self._engine = create_engine(self._connection_string)
            self._connection = self._engine.connect()
        except Exception as exc:
            raise TargetWriterConnectionError(
                f"cannot connect to target MSSQL database: {exc}"
            ) from exc
        for stmt in self._SESSION_STATEMENTS:
            self._exec(stmt)
        return self

    def __exit__(
        self,
        exc_type: Optional[type[BaseException]],
        exc: Optional[BaseException],
        tb: Optional[TracebackType],
    ) -> None:
        try:
            if self._connection is not None:
                if exc is None:
                    self._connection.commit()
                else:
                    self._connection.rollback()
                self._connection.close()
        finally:
            if self._engine is not None:
                self._engine.dispose()
            self._connection = None
            self._engine = None

    # ---- TargetWriter port ------------------------------------------------

    def execute_ddl(self, statement: str) -> None:
        self._exec(statement)

    def bulk_load(
        self,
        schema: str,
        table: Table,
        rows: Iterator[Tuple[Any, ...]],
    ) -> None:
        if not table.columns:
            return
        columns = ", ".join(self._quote_ident(name) for name in table.columns)
        placeholders = ", ".join(["%s"] * len(table.columns))
        qualified = f"{self._quote_ident(schema)}.{self._quote_ident(table.name)}"
        insert_sql = f"INSERT INTO {qualified} ({columns}) VALUES ({placeholders})"
        raw_cursor = self._raw_pymssql_cursor()
        total = 0
        batch: List[Tuple[Any, ...]] = []
        try:
            for row in rows:
                batch.append(row)
                if len(batch) >= self._batch_size:
                    raw_cursor.executemany(insert_sql, batch)
                    total += len(batch)
                    batch.clear()
            if batch:
                raw_cursor.executemany(insert_sql, batch)
                total += len(batch)
        except Exception as exc:
            raise TargetWriterExecutionError(f"INSERT into {qualified} failed: {exc}") from exc
        self._logger.info(f"loaded {total} row(s) into {schema}.{table.name}")

    # ---- helpers ----------------------------------------------------------

    def _exec(self, statement: str) -> None:
        if self._connection is None:
            raise TargetWriterExecutionError("writer is not connected")
        try:
            self._connection.execute(text(statement))
        except Exception as exc:
            raise TargetWriterExecutionError(
                f"failed to execute statement: {statement!r}: {exc}"
            ) from exc

    def _raw_pymssql_cursor(self) -> Any:
        if self._connection is None:
            raise TargetWriterExecutionError("writer is not connected")
        return self._connection.connection.cursor()

    @property
    def _connection_string(self) -> str:
        return build_url(self._config.target_server, "mssql+pymssql")

    @property
    def _connection_string_redacted(self) -> str:
        return redact_url(self._connection_string)

    def _quote_ident(self, name: str) -> str:
        # Must apply the same case policy as MssqlSqlEmitter.quote_identifier:
        # bulk_load targets the identifiers the emitted DDL just created.
        escaped = normalize_identifier(name, self._preserve_case).replace("]", "]]")
        return f"[{escaped}]"
