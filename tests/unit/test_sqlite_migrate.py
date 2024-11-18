"""DDL-identity golden test: the SQL DDL produced by the dump pipeline must be
strictly equal to the sequence of DDL statements executed by the migrate
pipeline. This is the invariant that lets us claim "dump == migrate" with a
real PostgresSqlEmitter (no mocking on the emitter side).
"""

from __future__ import annotations

import io
from pathlib import Path
from typing import Any, Iterator, List, Tuple

from db2sql.application.dto import DataFormat, MigrateRequest, OnExisting, TransactionMode
from db2sql.application.use_cases import DumpDatabaseUseCase, MigrateDatabaseUseCase
from db2sql.domain.model import Table
from db2sql.infrastructure.config import (
    AppConfig,
    DumpConfig,
    ServerConfig,
    to_dump_request,
    to_migrate_request,
)
from db2sql.infrastructure.emit.postgres import PostgresSqlEmitter
from db2sql.infrastructure.logging import ConsoleLogger, LEVEL_QUIET
from db2sql.infrastructure.output import ExecutingSink
from db2sql.infrastructure.persistence.sqlite import SQLiteSourceReader


class _BufferSink:
    def __init__(self) -> None:
        self.buffer = io.StringIO()

    def write(self, data: str) -> None:
        self.buffer.write(data)

    def boundary(self) -> None:
        pass

    def value(self) -> str:
        return self.buffer.getvalue()


class _RecordingWriter:
    """Fake TargetWriter that records execute_ddl + bulk_load calls."""

    def __init__(self) -> None:
        self.ddl_calls: List[str] = []
        self.bulk_loads: List[Tuple[str, str, int]] = []

    def __enter__(self) -> "_RecordingWriter":
        return self

    def __exit__(self, exc_type: Any, exc: Any, tb: Any) -> None:
        pass

    def execute_ddl(self, statement: str) -> None:
        self.ddl_calls.append(statement)

    def bulk_load(self, schema: str, table: Table, rows: Iterator[Tuple[Any, ...]]) -> None:
        consumed = list(rows)
        self.bulk_loads.append((schema, table.name, len(consumed)))


def _build_config(db_path: Path) -> AppConfig:
    return AppConfig(
        driver="sqlite",
        server=ServerConfig(dbname=str(db_path)),
        dump=DumpConfig(
            preserve_case=True,
            default_data_format=DataFormat.INSERT,
        ),
    )


def _normalize_statement(stmt: str) -> str:
    """Strip trailing whitespace + semicolons for fair statement-level comparison."""
    return stmt.strip().rstrip(";").strip()


def _split_dump_ddl(dump_output: str) -> List[str]:
    """Extract DDL statements from a dump output (in INSERT format).

    Filters out the per-row INSERT statements; what remains is the DDL the
    migrate pipeline must also execute.
    """
    stmts = [s.strip() for s in dump_output.split(";") if s.strip()]
    return [s for s in stmts if not s.lstrip().upper().startswith("INSERT ")]


def test_dump_ddl_equals_migrate_ddl(sample_db: Path) -> None:
    config = _build_config(sample_db)
    logger = ConsoleLogger(level=LEVEL_QUIET)

    # --- dump ---
    dump_reader = SQLiteSourceReader(config, logger)
    dump_emitter = PostgresSqlEmitter(preserve_case=True)
    dump_sink = _BufferSink()
    DumpDatabaseUseCase(
        reader=dump_reader,
        emitter=dump_emitter,
        sink=dump_sink,
        logger=logger,
        request=to_dump_request(config),
    ).execute()
    dump_ddl = [_normalize_statement(s) for s in _split_dump_ddl(dump_sink.value())]

    # --- migrate ---
    migrate_reader = SQLiteSourceReader(config, logger)
    migrate_emitter = PostgresSqlEmitter(preserve_case=True)
    writer = _RecordingWriter()
    with writer as live_writer:
        with ExecutingSink(live_writer) as exec_sink:
            MigrateDatabaseUseCase(
                reader=migrate_reader,
                emitter=migrate_emitter,
                sink=exec_sink,
                writer=live_writer,
                logger=logger,
                request=to_migrate_request(config),
            ).execute()
    migrate_ddl = [_normalize_statement(s) for s in writer.ddl_calls]

    assert dump_ddl == migrate_ddl, (
        "Migrate DDL differs from dump DDL.\n"
        f"DUMP:    {dump_ddl}\n"
        f"MIGRATE: {migrate_ddl}"
    )


def test_migrate_bulk_loads_every_table(sample_db: Path) -> None:
    """Sanity check: rows are routed through bulk_load (not execute_ddl)."""
    config = _build_config(sample_db)
    logger = ConsoleLogger(level=LEVEL_QUIET)
    reader = SQLiteSourceReader(config, logger)
    emitter = PostgresSqlEmitter(preserve_case=True)
    writer = _RecordingWriter()

    with writer as live_writer:
        with ExecutingSink(live_writer) as sink:
            MigrateDatabaseUseCase(
                reader=reader,
                emitter=emitter,
                sink=sink,
                writer=live_writer,
                logger=logger,
                request=to_migrate_request(config),
            ).execute()

    # author has 2 rows, book has 3 rows in the conftest fixture.
    loaded = {(schema, table): n for schema, table, n in writer.bulk_loads}
    assert loaded == {("public", "author"): 2, ("public", "book"): 3}
    # No INSERT statements leaked into execute_ddl.
    assert not any(s.lstrip().upper().startswith("INSERT ") for s in writer.ddl_calls)
