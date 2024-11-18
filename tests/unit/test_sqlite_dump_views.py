"""End-to-end view export against a real SQLite database."""

from __future__ import annotations

import io
from pathlib import Path

from db2sql.application.dto import DataFormat
from db2sql.application.use_cases import DumpDatabaseUseCase
from db2sql.infrastructure.config import (
    AppConfig,
    ColumnOverride,
    DumpConfig,
    ServerConfig,
    ViewExport,
    to_dump_request,
)
from db2sql.infrastructure.emit.postgres import PostgresSqlEmitter
from db2sql.infrastructure.logging import ConsoleLogger, LEVEL_QUIET
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


def _generate(config: AppConfig) -> str:
    logger = ConsoleLogger(level=LEVEL_QUIET)
    reader = SQLiteSourceReader(config, logger)
    emitter = PostgresSqlEmitter(
        preserve_case=config.dump.preserve_case,
        schema_mapping=dict(config.dump.mapping_schemas),
    )
    sink = _BufferSink()
    request = to_dump_request(config)
    DumpDatabaseUseCase(
        reader=reader,
        emitter=emitter,
        sink=sink,
        logger=logger,
        request=request,
    ).execute()
    return sink.value()


def test_view_creates_synthetic_table_with_inferred_schema_and_data(
    sample_db: Path,
) -> None:
    config = AppConfig(
        driver="sqlite",
        server=ServerConfig(dbname=str(sample_db)),
        dump=DumpConfig(
            preserve_case=True,
            views={
                "author_book_counts": ViewExport(
                    query=(
                        "SELECT a.id AS author_id, a.name AS author_name, "
                        "COUNT(b.id) AS book_count "
                        "FROM author a LEFT JOIN book b ON b.author_id = a.id "
                        "GROUP BY a.id, a.name ORDER BY a.id"
                    ),
                    primary_key=["author_id"],
                ),
            },
        ),
    )

    output = _generate(config)

    assert 'CREATE TABLE "public"."author_book_counts"' in output
    # The probe row provides the inferred types: int → integer, str → text.
    assert '"author_id" integer' in output
    assert '"author_name" text' in output
    assert '"book_count" integer' in output
    # primary_key option propagated through.
    assert 'PRIMARY KEY ("author_id")' in output
    # Data was streamed via the user-supplied query, not by SELECT * on a table.
    assert 'COPY "public"."author_book_counts"' in output
    assert "Alice" in output
    assert "Bob" in output


def test_view_column_override_replaces_inferred_type(sample_db: Path) -> None:
    config = AppConfig(
        driver="sqlite",
        server=ServerConfig(dbname=str(sample_db)),
        dump=DumpConfig(
            preserve_case=True,
            views={
                "vw": ViewExport(
                    query="SELECT id, name FROM author ORDER BY id",
                    columns={"name": ColumnOverride(type="varchar", char_length=255)},
                ),
            },
        ),
    )
    output = _generate(config)
    assert 'CREATE TABLE "public"."vw"' in output
    assert '"name" varchar(255)' in output


def test_view_insert_format_override(sample_db: Path) -> None:
    config = AppConfig(
        driver="sqlite",
        server=ServerConfig(dbname=str(sample_db)),
        dump=DumpConfig(
            preserve_case=True,
            views={
                "names": ViewExport(
                    query="SELECT name FROM author ORDER BY id",
                    data_format=DataFormat.INSERT,
                ),
            },
        ),
    )
    output = _generate(config)
    assert 'INSERT INTO "public"."names"' in output
    assert 'COPY "public"."names"' not in output


def test_view_limit_caps_row_count(sample_db: Path) -> None:
    config = AppConfig(
        driver="sqlite",
        server=ServerConfig(dbname=str(sample_db)),
        dump=DumpConfig(
            preserve_case=True,
            views={
                "two": ViewExport(
                    query="SELECT id FROM book ORDER BY id",
                    data_format=DataFormat.INSERT,
                    limit_records=2,
                ),
            },
        ),
    )
    output = _generate(config)
    insert_lines = [
        line for line in output.splitlines() if 'INSERT INTO "public"."two"' in line
    ]
    assert len(insert_lines) == 2
