"""Target writers: how the connection URL is built and how it is logged.

The rest of each writer needs a live server and is exercised by the
functional suite. These two properties are pure functions of the config, so
they are worth pinning here — they carry the ``--target-dsn`` path and the
password redaction, neither of which should wait for a database to be proven.
"""

from __future__ import annotations

from typing import Any, Tuple

import pytest

from db2sql.infrastructure.config import AppConfig, ConfigInvalidError, ServerConfig
from db2sql.infrastructure.writer.mssql import MssqlTargetWriter
from db2sql.infrastructure.writer.postgres import PostgresTargetWriter


class _StubLogger:
    def trace(self, message: str) -> None: ...
    def debug(self, message: str) -> None: ...
    def info(self, message: str) -> None: ...
    def warning(self, message: str) -> None: ...
    def error(self, message: str) -> None: ...


_WRITERS: Tuple[Tuple[Any, str, str], ...] = (
    (PostgresTargetWriter, "postgres", "postgresql+psycopg2"),
    (MssqlTargetWriter, "mssql", "mssql+pymssql"),
)


def _writer(writer_class: Any, target: str, **server: object) -> Any:
    config = AppConfig(target=target, target_server=ServerConfig(**server))
    return writer_class(config, _StubLogger())


@pytest.mark.parametrize(("writer_class", "target", "scheme"), _WRITERS)
def test_connection_string_is_built_from_the_target_server(
    writer_class: Any, target: str, scheme: str
) -> None:
    writer = _writer(
        writer_class, target, hostname="h", port=1234, username="u", password="p", dbname="d"
    )
    assert writer._connection_string == f"{scheme}://u:p@h:1234/d"


@pytest.mark.parametrize(("writer_class", "target", "scheme"), _WRITERS)
def test_connection_string_escapes_the_credentials(
    writer_class: Any, target: str, scheme: str
) -> None:
    writer = _writer(
        writer_class, target, hostname="h", username="u", password="p@ss/w", dbname="d"
    )
    assert writer._connection_string == f"{scheme}://u:p%40ss%2Fw@h/d"


@pytest.mark.parametrize(("writer_class", "target", "scheme"), _WRITERS)
def test_target_dsn_replaces_the_discrete_fields(
    writer_class: Any, target: str, scheme: str
) -> None:
    dsn = f"{scheme}://u:p@real:5432/db?connect_timeout=3"
    writer = _writer(writer_class, target, hostname="ignored", dsn=dsn)
    assert writer._connection_string == dsn


@pytest.mark.parametrize(("writer_class", "target", "scheme"), _WRITERS)
def test_target_dsn_of_another_dialect_is_rejected(
    writer_class: Any, target: str, scheme: str
) -> None:
    writer = _writer(writer_class, target, dsn="mysql+pymysql://u:p@h/db")
    with pytest.raises(ConfigInvalidError, match="does not match the selected driver"):
        _ = writer._connection_string


@pytest.mark.parametrize(("writer_class", "target", "scheme"), _WRITERS)
def test_redacted_connection_string_hides_the_password(
    writer_class: Any, target: str, scheme: str
) -> None:
    writer = _writer(
        writer_class, target, hostname="h", port=1234, username="u", password="s3cr3t", dbname="d"
    )
    redacted = writer._connection_string_redacted
    assert redacted == f"{scheme}://u:***@h:1234/d"
    assert "s3cr3t" not in redacted


@pytest.mark.parametrize(("writer_class", "target", "scheme"), _WRITERS)
def test_redacted_connection_string_hides_a_dsn_password(
    writer_class: Any, target: str, scheme: str
) -> None:
    writer = _writer(writer_class, target, dsn=f"{scheme}://u:s3cr3t@h/db")
    assert "s3cr3t" not in writer._connection_string_redacted
