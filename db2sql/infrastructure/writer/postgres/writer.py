"""PostgreSQL writer: execute DDL via SQLAlchemy + bulk-load via ``COPY FROM STDIN``.

Why COPY-text (not COPY-binary):
    psycopg2's ``copy_expert`` accepts the same text payload that ``psql -f`` would
    feed to the server. Producing that text here with the *same* per-value
    formatter the emitter uses for the file dump means the bytes hitting the
    server are byte-for-byte identical between dump and migrate. That keeps
    the identity invariant trivially provable.
"""

from __future__ import annotations

import io
from types import TracebackType
from typing import Any, Iterator, Optional, Tuple

from sqlalchemy import create_engine, text
from sqlalchemy.engine import Connection, Engine

from db2sql.application.ports import Logger
from db2sql.domain.model import Table
from db2sql.infrastructure.config import AppConfig
from db2sql.infrastructure.url import build_url, redact_url
from db2sql.infrastructure.writer.errors import (
    TargetWriterConnectionError,
    TargetWriterExecutionError,
)


class PostgresTargetWriter:
    """Live-migrate target writer for PostgreSQL."""

    _SESSION_STATEMENTS: Tuple[str, ...] = (
        "SET client_encoding TO 'UTF8'",
        "SET standard_conforming_strings TO on",
        "SET timezone TO 'UTC'",
    )

    def __init__(self, config: AppConfig, logger: Logger) -> None:
        self._config = config
        self._logger = logger
        self._engine: Optional[Engine] = None
        self._connection: Optional[Connection] = None

    # ---- lifecycle --------------------------------------------------------

    def __enter__(self) -> "PostgresTargetWriter":
        try:
            self._logger.info(f"connecting to target {self._connection_string_redacted}")
            self._engine = create_engine(self._connection_string)
            self._connection = self._engine.connect()
        except Exception as exc:
            raise TargetWriterConnectionError(
                f"cannot connect to target postgres database: {exc}"
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
        qualified = f"{self._quote_ident(schema)}.{self._quote_ident(table.name)}"
        copy_sql = f"COPY {qualified} ({columns}) FROM STDIN"
        buffer = io.StringIO()
        count = 0
        for row in rows:
            buffer.write("\t".join(self._format_copy_value(v) for v in row))
            buffer.write("\n")
            count += 1
        if count == 0:
            return
        buffer.seek(0)
        raw = self._raw_psycopg2_cursor()
        try:
            raw.copy_expert(copy_sql, buffer)
        except Exception as exc:
            raise TargetWriterExecutionError(f"COPY into {qualified} failed: {exc}") from exc
        self._logger.info(f"loaded {count} row(s) into {schema}.{table.name}")

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

    def _raw_psycopg2_cursor(self) -> Any:
        if self._connection is None:
            raise TargetWriterExecutionError("writer is not connected")
        return self._connection.connection.cursor()

    @property
    def _connection_string(self) -> str:
        return build_url(self._config.target_server, "postgresql+psycopg2")

    @property
    def _connection_string_redacted(self) -> str:
        return redact_url(self._connection_string)

    @staticmethod
    def _quote_ident(name: str) -> str:
        escaped = name.replace('"', '""')
        return f'"{escaped}"'

    # Mirrors PostgresSqlEmitter._format_copy_value so the bytes hitting the
    # server through COPY FROM STDIN are byte-identical to the file dump.
    @staticmethod
    def _format_copy_value(value: Any) -> str:
        if value is None:
            return r"\N"
        if isinstance(value, bool):
            return "t" if value else "f"
        if isinstance(value, (bytes, bytearray)):
            return "\\\\x" + bytes(value).hex()
        text_value = str(value)
        return (
            text_value.replace("\\", "\\\\")
            .replace("\t", "\\t")
            .replace("\n", "\\n")
            .replace("\r", "\\r")
        )
