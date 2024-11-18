"""Unit-ish integration tests: build a SQLite DB and inspect the generated SQL."""

from __future__ import annotations

import io
from pathlib import Path

from db2sql.application.dto import DataFormat
from db2sql.application.use_cases import DumpDatabaseUseCase
from db2sql.infrastructure.config import (
    AppConfig,
    DumpConfig,
    ServerConfig,
    to_dump_request,
)
from db2sql.infrastructure.emit.postgres import PostgresSqlEmitter
from db2sql.infrastructure.logging import ConsoleLogger, LEVEL_QUIET
from db2sql.infrastructure.persistence.sqlite import SQLiteSourceReader


def _build_config(db_path: Path, **overrides) -> AppConfig:
    dump_kwargs = {"preserve_case": True}
    dump_kwargs.update(overrides.get("dump", {}))
    return AppConfig(
        driver="sqlite",
        server=ServerConfig(dbname=str(db_path)),
        dump=DumpConfig(**dump_kwargs),
    )


class _BufferSink:
    def __init__(self) -> None:
        self.buffer = io.StringIO()

    def write(self, data: str) -> None:
        self.buffer.write(data)

    def boundary(self) -> None:
        pass

    def value(self) -> str:
        return self.buffer.getvalue()


def _generate(config: AppConfig) -> str:
    logger = ConsoleLogger(level=LEVEL_QUIET)
    reader = SQLiteSourceReader(config, logger)
    emitter = PostgresSqlEmitter(
        preserve_case=config.dump.preserve_case,
        schema_mapping=dict(config.dump.mapping_schemas),
    )
    sink = _BufferSink()
    request = to_dump_request(config)
    use_case = DumpDatabaseUseCase(
        reader=reader,
        emitter=emitter,
        sink=sink,
        logger=logger,
        request=request,
    )
    use_case.execute()
    return sink.value()


def test_copy_dump_contains_schema_tables_data_and_fk(sample_db: Path) -> None:
    config = _build_config(sample_db)
    output = _generate(config)

    assert "BEGIN;" in output
    assert "COMMIT;" in output
    assert 'CREATE SCHEMA IF NOT EXISTS "public"' in output
    assert 'CREATE TABLE "public"."author"' in output
    assert 'CREATE TABLE "public"."book"' in output
    assert "PRIMARY KEY" in output
    assert 'COPY "public"."author"' in output
    assert "Alice" in output
    assert "Second's ride" in output  # COPY single quotes are kept verbatim
    assert "\\N" in output  # NULL birth_year in COPY format
    assert "REFERENCES" in output
    assert 'CREATE INDEX "idx_book_title"' in output


def test_insert_format_per_table_override(sample_db: Path) -> None:
    config = _build_config(
        sample_db,
        dump={"tables": {"book": {"data_format": "insert"}}},
    )
    output = _generate(config)
    assert 'COPY "public"."author"' in output
    assert 'INSERT INTO "public"."book"' in output
    assert "Second''s ride" in output  # SQL-escaped single quote in INSERT


def test_data_format_cli_default_can_be_insert(sample_db: Path) -> None:
    config = _build_config(sample_db, dump={"default_data_format": DataFormat.INSERT})
    output = _generate(config)
    assert 'INSERT INTO "public"."author"' in output
    assert 'INSERT INTO "public"."book"' in output


def test_on_existing_drop_prepends_drops_before_creates(sample_db: Path) -> None:
    config = _build_config(sample_db, dump={"on_existing": "drop"})
    output = _generate(config)

    drop_author = output.index('DROP TABLE IF EXISTS "public"."author";')
    drop_book = output.index('DROP TABLE IF EXISTS "public"."book";')
    create_author = output.index('CREATE TABLE "public"."author"')
    create_book = output.index('CREATE TABLE "public"."book"')

    # all DROPs appear before any CREATE
    assert max(drop_author, drop_book) < min(create_author, create_book)
    # book references author → book is dropped first, author last
    assert drop_book < drop_author


def test_on_existing_fail_omits_drops(sample_db: Path) -> None:
    config = _build_config(sample_db)  # default is fail
    output = _generate(config)
    assert "DROP TABLE IF EXISTS" not in output


def test_on_existing_truncate_emits_data_only_script(sample_db: Path) -> None:
    config = _build_config(sample_db, dump={"on_existing": "truncate"})
    output = _generate(config)

    # No DDL whatsoever
    assert "CREATE SCHEMA" not in output
    assert "CREATE TABLE" not in output
    assert "REFERENCES" not in output
    assert "CREATE INDEX" not in output
    # Single TRUNCATE statement listing both tables with RESTART IDENTITY
    assert output.count("TRUNCATE TABLE") == 1
    assert '"public"."author"' in output
    assert '"public"."book"' in output
    assert "RESTART IDENTITY" in output
    # Data is still loaded after TRUNCATE
    truncate_idx = output.index("TRUNCATE TABLE")
    copy_idx = output.index('COPY "public"."author"')
    assert truncate_idx < copy_idx
