"""No reader may write a source password to the log when opening its session."""

from __future__ import annotations

from typing import Any, List
from unittest.mock import patch

import pytest

from db2sql.infrastructure.config import AppConfig, ServerConfig
from db2sql.infrastructure.persistence.mssql.reader import MSSQLSourceReader
from db2sql.infrastructure.persistence.mysql.reader import MySQLSourceReader
from db2sql.infrastructure.persistence.oracle.reader import OracleSourceReader
from db2sql.infrastructure.persistence.postgres.reader import PostgresSourceReader
from db2sql.infrastructure.persistence.sqlite.reader import SQLiteSourceReader

_PASSWORD = "sup3r-s3cr3t"


class _RecordingLogger:
    def __init__(self) -> None:
        self.messages: List[str] = []

    def trace(self, message: str) -> None: ...
    def debug(self, message: str) -> None: ...
    def warning(self, message: str) -> None: ...
    def error(self, message: str) -> None: ...

    def info(self, message: str) -> None:
        self.messages.append(message)


_READERS = [
    (PostgresSourceReader, "postgres", "db2sql.infrastructure.persistence.postgres.reader"),
    (MySQLSourceReader, "mysql", "db2sql.infrastructure.persistence.mysql.reader"),
    (MSSQLSourceReader, "mssql", "db2sql.infrastructure.persistence.mssql.reader"),
    (OracleSourceReader, "oracle", "db2sql.infrastructure.persistence.oracle.reader"),
]


@pytest.mark.parametrize(("reader_class", "driver", "module"), _READERS)
def test_reader_never_logs_the_password(reader_class: Any, driver: str, module: str) -> None:
    config = AppConfig(
        driver=driver,
        server=ServerConfig(
            hostname="db.local", port=1234, username="u", password=_PASSWORD, dbname="d"
        ),
    )
    logger = _RecordingLogger()
    reader = reader_class(config, logger)

    with patch(f"{module}.create_engine"), patch(f"{module}.sessionmaker"):
        reader._ensure_session()

    logged = "\n".join(logger.messages)
    assert logged, "the reader is expected to log the connection it opens"
    assert _PASSWORD not in logged
    assert ":***@" in logged


def test_sqlite_reader_logs_its_path() -> None:
    """SQLite has no credentials — the URL must still be logged, unmangled."""
    config = AppConfig(driver="sqlite", server=ServerConfig(dbname="/tmp/x.db"))
    logger = _RecordingLogger()
    reader = SQLiteSourceReader(config, logger)

    module = "db2sql.infrastructure.persistence.sqlite.reader"
    with patch(f"{module}.create_engine"), patch(f"{module}.sessionmaker"):
        reader._ensure_session()

    assert "sqlite:////tmp/x.db" in "\n".join(logger.messages)
