"""Target writers quote identifiers under the same case policy as the emitters.

``migrate`` creates the schema with the emitter's DDL and then bulk-loads into
it through the writer. If the two disagree on case, the DDL creates
``my_table`` while the load targets ``"MyTable"`` and the migration fails on a
table that was just created.
"""

from __future__ import annotations

from typing import Any, Tuple

import pytest

from db2sql.infrastructure.config import AppConfig, DumpConfig
from db2sql.infrastructure.emit.mssql import MssqlSqlEmitter
from db2sql.infrastructure.emit.postgres import PostgresSqlEmitter
from db2sql.infrastructure.writer.mssql import MssqlTargetWriter
from db2sql.infrastructure.writer.postgres import PostgresTargetWriter


class _StubLogger:
    def trace(self, message: str) -> None: ...
    def debug(self, message: str) -> None: ...
    def info(self, message: str) -> None: ...
    def warning(self, message: str) -> None: ...
    def error(self, message: str) -> None: ...


_PAIRS: Tuple[Tuple[Any, Any, str], ...] = (
    (PostgresTargetWriter, PostgresSqlEmitter, "postgres"),
    (MssqlTargetWriter, MssqlSqlEmitter, "mssql"),
)


def _writer(writer_class: Any, target: str, preserve_case: bool) -> Any:
    config = AppConfig(target=target, dump=DumpConfig(preserve_case=preserve_case))
    return writer_class(config, _StubLogger())


@pytest.mark.parametrize(("writer_class", "emitter_class", "target"), _PAIRS)
@pytest.mark.parametrize("preserve_case", [True, False])
def test_writer_quoting_matches_the_emitter(
    writer_class: Any, emitter_class: Any, target: str, preserve_case: bool
) -> None:
    writer = _writer(writer_class, target, preserve_case)
    emitter = emitter_class(preserve_case=preserve_case)
    assert writer._quote_ident("MyTable") == emitter.quote_identifier("MyTable")


@pytest.mark.parametrize(("writer_class", "emitter_class", "target"), _PAIRS)
def test_snake_case_is_applied_when_case_is_not_preserved(
    writer_class: Any, emitter_class: Any, target: str
) -> None:
    writer = _writer(writer_class, target, preserve_case=False)
    assert "my_table" in writer._quote_ident("MyTable")
