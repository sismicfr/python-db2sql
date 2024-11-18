"""Unit tests for :class:`ExecutingSink`."""

from __future__ import annotations

from typing import Any, Iterator, List, Tuple

from db2sql.domain.model import Table
from db2sql.infrastructure.output import ExecutingSink


class _RecordingWriter:
    def __init__(self) -> None:
        self.calls: List[str] = []

    def __enter__(self) -> "_RecordingWriter":
        return self

    def __exit__(self, *args: Any) -> None:
        pass

    def execute_ddl(self, statement: str) -> None:
        self.calls.append(statement)

    def bulk_load(self, schema: str, table: Table, rows: Iterator[Tuple[Any, ...]]) -> None:
        pass


def test_splits_on_semicolon_newline() -> None:
    writer = _RecordingWriter()
    with ExecutingSink(writer) as sink:
        sink.write("CREATE SCHEMA \"public\";\n")
        sink.write("CREATE TABLE foo (id int);\n")
    assert writer.calls == ['CREATE SCHEMA "public";', "CREATE TABLE foo (id int);"]


def test_buffers_partial_statements_across_writes() -> None:
    writer = _RecordingWriter()
    with ExecutingSink(writer) as sink:
        sink.write("CREATE TABLE foo (\n")
        sink.write("    id int,\n")
        sink.write("    name text\n")
        sink.write(");\n")
    assert writer.calls == ["CREATE TABLE foo (\n    id int,\n    name text\n);"]


def test_multiple_statements_in_single_write() -> None:
    writer = _RecordingWriter()
    with ExecutingSink(writer) as sink:
        sink.write("BEGIN;\nCREATE TABLE a (id int);\nCOMMIT;\n")
    assert writer.calls == ["BEGIN;", "CREATE TABLE a (id int);", "COMMIT;"]


def test_ignores_empty_or_whitespace_statements() -> None:
    writer = _RecordingWriter()
    with ExecutingSink(writer) as sink:
        sink.write(";\n\n;\nSELECT 1;\n;\n")
    assert writer.calls == ["SELECT 1;"]


def test_flush_executes_unterminated_buffer() -> None:
    writer = _RecordingWriter()
    with ExecutingSink(writer) as sink:
        sink.write("SELECT 1")  # No trailing ;
    # On context exit, flush() is called and the remaining buffer is executed.
    assert writer.calls == ["SELECT 1"]
