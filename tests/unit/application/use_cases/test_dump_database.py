"""DumpDatabaseUseCase orchestration tests using fake adapters.

These tests do not touch any database — they exercise the use case against
in-memory fakes for the four ports (SourceReader, SqlEmitter, OutputSink, Logger).
"""

from __future__ import annotations

from typing import Any, Iterable, Iterator, List, Tuple

import pytest

from db2sql.application.dto import (
    DataFormat,
    DumpOptions,
    DumpRequest,
    OnExisting,
    TableOption,
)
from db2sql.application.use_cases import DumpDatabaseUseCase
from db2sql.domain.model import Column, Database, Schema, Table
from db2sql.domain.policy import FilterRules


# --- fakes -----------------------------------------------------------------


class FakeSink:
    def __init__(self) -> None:
        self.buffer: List[str] = []

    def write(self, data: str) -> None:
        self.buffer.append(data)

    def boundary(self) -> None:
        pass

    @property
    def text(self) -> str:
        return "".join(self.buffer)


class FakeLogger:
    def __init__(self) -> None:
        self.messages: List[Tuple[str, str]] = []

    def trace(self, message: str) -> None:
        self.messages.append(("trace", message))

    def debug(self, message: str) -> None:
        self.messages.append(("debug", message))

    def info(self, message: str) -> None:
        self.messages.append(("info", message))

    def warning(self, message: str) -> None:
        self.messages.append(("warning", message))

    def error(self, message: str) -> None:
        self.messages.append(("error", message))


class FakeReader:
    def __init__(self, database: Database) -> None:
        self._database = database
        self.iter_calls: List[Tuple[str, str, int]] = []
        self.collect_called = 0

    def collect_metadata(self) -> Database:
        self.collect_called += 1
        return self._database

    def iter_rows(
        self, schema: str, table: Table, limit: int = -1
    ) -> Iterator[Tuple[Any, ...]]:
        self.iter_calls.append((schema, table.name, limit))
        # Emit one synthetic row per call
        yield (1, "row")


class FakeEmitter:
    def __init__(self) -> None:
        self.calls: List[str] = []
        # Capture the DBs/tables we see for assertions
        self.last_database: Database = None  # type: ignore[assignment]
        self.copy_tables: List[str] = []
        self.insert_tables: List[str] = []

    def emit_prologue(self, sink: Any) -> None:
        self.calls.append("prologue")
        sink.write("BEGIN;\n\n")

    def emit_epilogue(self, sink: Any) -> None:
        self.calls.append("epilogue")
        sink.write("COMMIT;\n")

    def emit_schemas(self, database: Database, sink: Any) -> None:
        self.last_database = database
        self.calls.append("schemas")
        sink.write("-- schemas --\n")

    def emit_drops(self, database: Database, sink: Any) -> None:
        self.calls.append("drops")
        sink.write("-- drops --\n")

    def emit_truncates(self, database: Database, sink: Any) -> None:
        self.calls.append("truncates")
        sink.write("-- truncates --\n")

    def emit_tables(self, database: Database, sink: Any) -> None:
        self.calls.append("tables")
        sink.write("-- tables --\n")

    def emit_foreign_keys(self, database: Database, sink: Any) -> None:
        self.calls.append("foreign_keys")
        sink.write("-- fks --\n")

    def emit_indexes(self, database: Database, sink: Any) -> None:
        self.calls.append("indexes")
        sink.write("-- indexes --\n")

    def emit_data_copy(
        self,
        schema: Schema,
        table: Table,
        rows: Iterable[Iterable[Any]],
        sink: Any,
    ) -> None:
        self.calls.append(f"copy:{schema.name}.{table.name}")
        self.copy_tables.append(f"{schema.name}.{table.name}")
        # Drain rows to ensure the reader generator is consumed
        list(rows)
        sink.write(f"-- copy {schema.name}.{table.name} --\n")

    def emit_data_insert(
        self,
        schema: Schema,
        table: Table,
        rows: Iterable[Iterable[Any]],
        sink: Any,
    ) -> None:
        self.calls.append(f"insert:{schema.name}.{table.name}")
        self.insert_tables.append(f"{schema.name}.{table.name}")
        list(rows)
        sink.write(f"-- insert {schema.name}.{table.name} --\n")


# --- helpers ----------------------------------------------------------------


def _build_database() -> Database:
    db = Database(name="main")
    public = Schema(name="public")
    author = Table(name="author")
    author.add_column(Column(name="id", type="int", constraint="PRIMARY KEY", identity=True))
    public.add_table(author)
    book = Table(name="book")
    book.add_column(Column(name="id", type="int", constraint="PRIMARY KEY"))
    public.add_table(book)
    db.add_schema(public)
    return db


def _build(
    *,
    database: Database = None,  # type: ignore[assignment]
    request: DumpRequest = None,  # type: ignore[assignment]
) -> Tuple[DumpDatabaseUseCase, FakeReader, FakeEmitter, FakeSink, FakeLogger]:
    database = database or _build_database()
    request = request or DumpRequest(options=DumpOptions(), filter_rules=FilterRules())
    reader = FakeReader(database)
    emitter = FakeEmitter()
    sink = FakeSink()
    logger = FakeLogger()
    use_case = DumpDatabaseUseCase(
        reader=reader, emitter=emitter, sink=sink, logger=logger, request=request
    )
    return use_case, reader, emitter, sink, logger


# --- tests ------------------------------------------------------------------


class TestDumpDatabaseUseCase:
    def test_emits_full_pipeline_in_correct_order(self) -> None:
        use_case, reader, emitter, sink, _ = _build()
        use_case.execute()

        assert reader.collect_called == 1
        # the first emitter call is prologue, then schemas, tables, data, fks, indexes, epilogue
        assert emitter.calls == [
            "prologue",
            "schemas",
            "tables",
            "copy:public.author",
            "copy:public.book",
            "foreign_keys",
            "indexes",
            "epilogue",
        ]
        assert sink.text.startswith("BEGIN;\n\n")
        assert sink.text.endswith("COMMIT;\n")

    def test_default_format_is_copy(self) -> None:
        use_case, _, emitter, _, _ = _build()
        use_case.execute()
        assert emitter.copy_tables == ["public.author", "public.book"]
        assert emitter.insert_tables == []

    def test_per_table_format_override_is_honored(self) -> None:
        request = DumpRequest(
            options=DumpOptions(
                default_data_format=DataFormat.COPY,
                table_options={"public.book": TableOption(data_format=DataFormat.INSERT)},
            ),
            filter_rules=FilterRules(),
        )
        use_case, _, emitter, _, _ = _build(request=request)
        use_case.execute()
        assert emitter.copy_tables == ["public.author"]
        assert emitter.insert_tables == ["public.book"]

    def test_zero_limit_skips_data_emission_for_table(self) -> None:
        request = DumpRequest(
            options=DumpOptions(
                table_options={"public.author": TableOption(limit_records=0)},
            ),
            filter_rules=FilterRules(),
        )
        use_case, reader, emitter, _, _ = _build(request=request)
        use_case.execute()

        # author was skipped — no iter_rows call, no emit call
        assert reader.iter_calls == [("public", "book", -1)]
        assert emitter.copy_tables == ["public.book"]

    def test_filter_rules_remove_tables_before_emit(self) -> None:
        request = DumpRequest(
            options=DumpOptions(),
            filter_rules=FilterRules(exclude_tables=frozenset({"book"})),
        )
        use_case, reader, emitter, _, _ = _build(request=request)
        use_case.execute()

        # the emitter saw only the filtered database — book is gone
        emitted = emitter.last_database
        assert list(emitted.schemas["public"].tables) == ["author"]
        # iter_rows was never called for book
        assert reader.iter_calls == [("public", "author", -1)]

    def test_filter_rules_do_not_mutate_original_database(self) -> None:
        source = _build_database()
        request = DumpRequest(
            options=DumpOptions(),
            filter_rules=FilterRules(exclude_tables=frozenset({"book"})),
        )
        use_case, _, _, _, _ = _build(database=source, request=request)
        use_case.execute()

        assert "book" in source.schemas["public"].tables

    def test_global_limit_is_passed_to_reader(self) -> None:
        request = DumpRequest(
            options=DumpOptions(limit_records=42),
            filter_rules=FilterRules(),
        )
        use_case, reader, _, _, _ = _build(request=request)
        use_case.execute()

        assert reader.iter_calls == [("public", "author", 42), ("public", "book", 42)]

    def test_per_table_limit_override(self) -> None:
        request = DumpRequest(
            options=DumpOptions(
                limit_records=100,
                table_options={"public.book": TableOption(limit_records=5)},
            ),
            filter_rules=FilterRules(),
        )
        use_case, reader, _, _, _ = _build(request=request)
        use_case.execute()

        assert reader.iter_calls == [("public", "author", 100), ("public", "book", 5)]

    def test_logger_announces_each_dumped_table(self) -> None:
        use_case, _, _, _, logger = _build()
        use_case.execute()

        info_lines = [msg for level, msg in logger.messages if level == "info"]
        assert "dumping rows from public.author (copy)" in info_lines
        assert "dumping rows from public.book (copy)" in info_lines

    def test_returns_the_filtered_database(self) -> None:
        request = DumpRequest(
            options=DumpOptions(),
            filter_rules=FilterRules(exclude_tables=frozenset({"book"})),
        )
        use_case, _, _, _, _ = _build(request=request)
        result = use_case.execute()
        assert isinstance(result, Database)
        assert list(result.schemas["public"].tables) == ["author"]

    def test_empty_database_still_emits_begin_and_commit(self) -> None:
        empty = Database(name="empty")
        use_case, _, emitter, sink, _ = _build(database=empty)
        use_case.execute()
        assert sink.text.startswith("BEGIN;\n\n")
        assert sink.text.endswith("COMMIT;\n")
        # prologue/schemas/tables/fks/indexes/epilogue are still called even when empty
        assert emitter.calls == [
            "prologue",
            "schemas",
            "tables",
            "foreign_keys",
            "indexes",
            "epilogue",
        ]

    def test_on_existing_fail_does_not_emit_drops(self) -> None:
        request = DumpRequest(
            options=DumpOptions(),
            filter_rules=FilterRules(),
            on_existing=OnExisting.FAIL,
        )
        use_case, _, emitter, _, _ = _build(request=request)
        use_case.execute()
        assert "drops" not in emitter.calls

    def test_on_existing_drop_emits_drops_between_schemas_and_tables(self) -> None:
        request = DumpRequest(
            options=DumpOptions(),
            filter_rules=FilterRules(),
            on_existing=OnExisting.DROP,
        )
        use_case, _, emitter, _, _ = _build(request=request)
        use_case.execute()
        idx_schemas = emitter.calls.index("schemas")
        idx_drops = emitter.calls.index("drops")
        idx_tables = emitter.calls.index("tables")
        assert idx_schemas < idx_drops < idx_tables
        assert emitter.calls.count("drops") == 1

    def test_on_existing_truncate_emits_data_only_script(self) -> None:
        request = DumpRequest(
            options=DumpOptions(),
            filter_rules=FilterRules(),
            on_existing=OnExisting.TRUNCATE,
        )
        use_case, _, emitter, _, _ = _build(request=request)
        use_case.execute()
        # DDL-emitting calls must be absent
        for call in ("schemas", "tables", "drops", "foreign_keys", "indexes"):
            assert call not in emitter.calls, f"{call} should be skipped in truncate mode"
        # truncate runs once, between prologue and the data emission
        assert emitter.calls.count("truncates") == 1
        idx_prologue = emitter.calls.index("prologue")
        idx_truncates = emitter.calls.index("truncates")
        idx_first_copy = next(i for i, c in enumerate(emitter.calls) if c.startswith("copy:"))
        idx_epilogue = emitter.calls.index("epilogue")
        assert idx_prologue < idx_truncates < idx_first_copy < idx_epilogue

    def test_use_transaction_false_skips_prologue_and_epilogue(self) -> None:
        request = DumpRequest(
            options=DumpOptions(),
            filter_rules=FilterRules(),
            use_transaction=False,
        )
        use_case, _, emitter, sink, _ = _build(request=request)
        use_case.execute()
        assert "prologue" not in emitter.calls
        assert "epilogue" not in emitter.calls
        assert "BEGIN" not in sink.text
        assert "COMMIT" not in sink.text
        # The rest of the pipeline must still run in order.
        assert emitter.calls == [
            "schemas",
            "tables",
            "copy:public.author",
            "copy:public.book",
            "foreign_keys",
            "indexes",
        ]
