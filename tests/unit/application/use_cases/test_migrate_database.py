"""MigrateDatabaseUseCase orchestration tests using fake adapters.

The DDL-identity invariant — same emit_* calls in the same order as the dump
use case — is verified against an in-memory fake emitter and writer.
"""

from __future__ import annotations

from typing import Any, Iterator, List, Tuple

from db2sql.application.dto import (
    DumpOptions,
    MigrateRequest,
    OnExisting,
    TransactionMode,
)
from db2sql.application.use_cases import DumpDatabaseUseCase, MigrateDatabaseUseCase
from db2sql.application.dto import DumpRequest
from db2sql.domain.model import Column, Database, Schema, Table
from db2sql.domain.policy import FilterRules


# --- fakes -----------------------------------------------------------------


class FakeSink:
    def __init__(self) -> None:
        self.calls: List[str] = []

    def write(self, data: str) -> None:
        self.calls.append(data)

    def boundary(self) -> None:
        pass


class FakeLogger:
    def __init__(self) -> None:
        self.messages: List[Tuple[str, str]] = []

    def trace(self, message: str) -> None: self.messages.append(("trace", message))
    def debug(self, message: str) -> None: self.messages.append(("debug", message))
    def info(self, message: str) -> None: self.messages.append(("info", message))
    def warning(self, message: str) -> None: self.messages.append(("warning", message))
    def error(self, message: str) -> None: self.messages.append(("error", message))


class FakeReader:
    def __init__(self, database: Database) -> None:
        self._database = database
        self.iter_calls: List[Tuple[str, str, int]] = []

    def collect_metadata(self) -> Database:
        return self._database

    def iter_rows(self, schema: str, table: Table, limit: int = -1) -> Iterator[Tuple[Any, ...]]:
        self.iter_calls.append((schema, table.name, limit))
        yield (1, "row")

    def describe_query(self, query: str) -> List[Column]:
        return []

    def iter_query_rows(self, query: str, limit: int = -1) -> Iterator[Tuple[Any, ...]]:
        yield from ()


class RecordingEmitter:
    """Records the sequence of emit_* method names called on it."""

    def __init__(self) -> None:
        self.calls: List[str] = []

    def emit_prologue(self, sink: Any) -> None:
        self.calls.append("emit_prologue")

    def emit_epilogue(self, sink: Any) -> None:
        self.calls.append("emit_epilogue")

    def emit_schemas(self, database: Database, sink: Any) -> None:
        self.calls.append("emit_schemas")

    def emit_drops(self, database: Database, sink: Any) -> None:
        self.calls.append("emit_drops")

    def emit_truncates(self, database: Database, sink: Any) -> None:
        self.calls.append("emit_truncates")

    def emit_tables(self, database: Database, sink: Any) -> None:
        self.calls.append("emit_tables")

    def emit_foreign_keys(self, database: Database, sink: Any) -> None:
        self.calls.append("emit_foreign_keys")

    def emit_indexes(self, database: Database, sink: Any) -> None:
        self.calls.append("emit_indexes")

    def emit_data_copy(self, schema, table, rows, sink) -> None:
        self.calls.append(f"emit_data_copy:{schema.name}.{table.name}")

    def emit_data_insert(self, schema, table, rows, sink) -> None:
        self.calls.append(f"emit_data_insert:{schema.name}.{table.name}")


class FakeWriter:
    def __init__(self) -> None:
        self.bulk_loads: List[Tuple[str, str, int]] = []
        self.ddl_calls: List[str] = []

    def __enter__(self) -> "FakeWriter":
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        pass

    def execute_ddl(self, statement: str) -> None:
        self.ddl_calls.append(statement)

    def bulk_load(self, schema: str, table: Table, rows: Iterator[Tuple[Any, ...]]) -> None:
        consumed = list(rows)
        self.bulk_loads.append((schema, table.name, len(consumed)))


# --- helpers ---------------------------------------------------------------


def _build_database() -> Database:
    db = Database("sample")
    public = Schema("public")
    author = Table("author")
    author.add_column(Column(name="id", type="integer", constraint="PRIMARY KEY"))
    author.add_column(Column(name="name", type="text", nullable=False))
    public.add_table(author)
    book = Table("book")
    book.add_column(Column(name="id", type="integer", constraint="PRIMARY KEY"))
    book.add_column(Column(name="title", type="text", nullable=False))
    public.add_table(book)
    db.add_schema(public)
    return db


def _dump_request() -> DumpRequest:
    return DumpRequest(
        options=DumpOptions(),
        filter_rules=FilterRules(),
    )


def _migrate_request() -> MigrateRequest:
    return MigrateRequest(
        options=DumpOptions(),
        filter_rules=FilterRules(),
        on_existing=OnExisting.FAIL,
        transaction_mode=TransactionMode.SINGLE,
    )


# --- tests -----------------------------------------------------------------


def test_migrate_emits_same_ddl_method_sequence_as_dump() -> None:
    """The DDL-identity invariant: emit_* methods are called in the same order."""
    db = _build_database()

    dump_emitter = RecordingEmitter()
    dump_use_case = DumpDatabaseUseCase(
        reader=FakeReader(db),
        emitter=dump_emitter,
        sink=FakeSink(),
        logger=FakeLogger(),
        request=_dump_request(),
    )
    dump_use_case.execute()

    migrate_emitter = RecordingEmitter()
    migrate_use_case = MigrateDatabaseUseCase(
        reader=FakeReader(db),
        emitter=migrate_emitter,
        sink=FakeSink(),
        writer=FakeWriter(),
        logger=FakeLogger(),
        request=_migrate_request(),
    )
    migrate_use_case.execute()

    # Strip the data-method calls — they intentionally differ (dump emits to
    # the sink, migrate routes to writer.bulk_load).
    def ddl_only(calls: List[str]) -> List[str]:
        return [c for c in calls if not c.startswith("emit_data_")]

    assert ddl_only(dump_emitter.calls) == ddl_only(migrate_emitter.calls)


def test_migrate_routes_data_to_bulk_load_not_emitter() -> None:
    db = _build_database()
    emitter = RecordingEmitter()
    writer = FakeWriter()

    use_case = MigrateDatabaseUseCase(
        reader=FakeReader(db),
        emitter=emitter,
        sink=FakeSink(),
        writer=writer,
        logger=FakeLogger(),
        request=_migrate_request(),
    )
    use_case.execute()

    # No emit_data_* calls on the emitter side.
    assert not any(c.startswith("emit_data_") for c in emitter.calls)
    # Every table got a bulk_load call with one row from FakeReader.
    assert writer.bulk_loads == [("public", "author", 1), ("public", "book", 1)]


def test_migrate_on_existing_drop_invokes_emit_drops_between_schemas_and_tables() -> None:
    db = _build_database()
    emitter = RecordingEmitter()
    request = MigrateRequest(
        options=DumpOptions(),
        filter_rules=FilterRules(),
        on_existing=OnExisting.DROP,
    )

    use_case = MigrateDatabaseUseCase(
        reader=FakeReader(db),
        emitter=emitter,
        sink=FakeSink(),
        writer=FakeWriter(),
        logger=FakeLogger(),
        request=request,
    )
    use_case.execute()

    idx_schemas = emitter.calls.index("emit_schemas")
    idx_drops = emitter.calls.index("emit_drops")
    idx_tables = emitter.calls.index("emit_tables")
    assert idx_schemas < idx_drops < idx_tables


def test_migrate_on_existing_fail_does_not_invoke_emit_drops() -> None:
    db = _build_database()
    emitter = RecordingEmitter()
    use_case = MigrateDatabaseUseCase(
        reader=FakeReader(db),
        emitter=emitter,
        sink=FakeSink(),
        writer=FakeWriter(),
        logger=FakeLogger(),
        request=_migrate_request(),
    )
    use_case.execute()
    assert "emit_drops" not in emitter.calls


def test_migrate_on_existing_truncate_skips_ddl_and_invokes_truncate() -> None:
    db = _build_database()
    emitter = RecordingEmitter()
    writer = FakeWriter()
    request = MigrateRequest(
        options=DumpOptions(),
        filter_rules=FilterRules(),
        on_existing=OnExisting.TRUNCATE,
    )
    use_case = MigrateDatabaseUseCase(
        reader=FakeReader(db),
        emitter=emitter,
        sink=FakeSink(),
        writer=writer,
        logger=FakeLogger(),
        request=request,
    )
    use_case.execute()

    for call in ("emit_schemas", "emit_tables", "emit_drops",
                 "emit_foreign_keys", "emit_indexes"):
        assert call not in emitter.calls
    assert emitter.calls.count("emit_truncates") == 1
    idx_prologue = emitter.calls.index("emit_prologue")
    idx_truncate = emitter.calls.index("emit_truncates")
    idx_epilogue = emitter.calls.index("emit_epilogue")
    assert idx_prologue < idx_truncate < idx_epilogue
    # bulk_load still happens — data refresh is the whole point
    assert writer.bulk_loads == [("public", "author", 1), ("public", "book", 1)]


def test_migrate_use_transaction_false_skips_prologue_and_epilogue() -> None:
    db = _build_database()
    emitter = RecordingEmitter()
    request = MigrateRequest(
        options=DumpOptions(),
        filter_rules=FilterRules(),
        use_transaction=False,
    )
    use_case = MigrateDatabaseUseCase(
        reader=FakeReader(db),
        emitter=emitter,
        sink=FakeSink(),
        writer=FakeWriter(),
        logger=FakeLogger(),
        request=request,
    )
    use_case.execute()

    assert "emit_prologue" not in emitter.calls
    assert "emit_epilogue" not in emitter.calls
    # Rest of the DDL pipeline still runs.
    assert emitter.calls == [
        "emit_schemas",
        "emit_tables",
        "emit_foreign_keys",
        "emit_indexes",
    ]


def test_migrate_skips_tables_with_zero_limit() -> None:
    db = _build_database()
    from db2sql.application.dto import TableOption

    request = MigrateRequest(
        options=DumpOptions(
            table_options={"public.book": TableOption(limit_records=0)},
        ),
        filter_rules=FilterRules(),
    )
    writer = FakeWriter()

    use_case = MigrateDatabaseUseCase(
        reader=FakeReader(db),
        emitter=RecordingEmitter(),
        sink=FakeSink(),
        writer=writer,
        logger=FakeLogger(),
        request=request,
    )
    use_case.execute()

    assert writer.bulk_loads == [("public", "author", 1)]
