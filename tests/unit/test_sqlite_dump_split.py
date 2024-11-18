"""Dump pipeline with --split-size: concatenated parts must match the unsplit dump."""

from __future__ import annotations

import io
from pathlib import Path

from db2sql.application.use_cases import DumpDatabaseUseCase
from db2sql.infrastructure.config import (
    AppConfig,
    DumpConfig,
    ServerConfig,
    to_dump_request,
)
from db2sql.infrastructure.emit.postgres import PostgresSqlEmitter
from db2sql.infrastructure.logging import ConsoleLogger, LEVEL_QUIET
from db2sql.infrastructure.output import RotatingFileSink
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


def _config(db_path: Path, output_file: str | None = None) -> AppConfig:
    return AppConfig(
        driver="sqlite",
        server=ServerConfig(dbname=str(db_path)),
        dump=DumpConfig(preserve_case=True),
        output_file=output_file,
    )


def _make_use_case(config: AppConfig, sink: object) -> DumpDatabaseUseCase:
    logger = ConsoleLogger(level=LEVEL_QUIET)
    reader = SQLiteSourceReader(config, logger)
    emitter = PostgresSqlEmitter(preserve_case=config.dump.preserve_case)
    request = to_dump_request(config)
    return DumpDatabaseUseCase(
        reader=reader, emitter=emitter, sink=sink, logger=logger, request=request,
    )


def test_split_concatenation_matches_unsplit_output(sample_db: Path, tmp_path: Path) -> None:
    # Reference: unsplit dump.
    ref = _BufferSink()
    _make_use_case(_config(sample_db), ref).execute()
    expected = ref.value()

    # Split: small max_bytes so several rotations happen on this small DB.
    out = tmp_path / "dump.sql"
    with RotatingFileSink(str(out), max_bytes=128) as sink:
        _make_use_case(_config(sample_db, str(out)), sink).execute()
        parts = sink.paths

    assert len(parts) > 1, "expected the dump to be split into multiple files"
    combined = "".join(p.read_text() for p in parts)
    assert combined == expected


def test_no_part_ends_inside_a_copy_block(sample_db: Path, tmp_path: Path) -> None:
    out = tmp_path / "dump.sql"
    with RotatingFileSink(str(out), max_bytes=64) as sink:
        _make_use_case(_config(sample_db, str(out)), sink).execute()
        parts = sink.paths

    for part in parts:
        text = part.read_text()
        # An open COPY block (with FROM stdin) must be closed by \. in the same file.
        if "FROM stdin;" in text:
            assert "\\.\n" in text, f"unterminated COPY in {part.name}"
        # A part may not start mid-COPY: it must not contain a lone trailing \.
        # without a matching opener.
        opens = text.count("FROM stdin;")
        closes = text.count("\\.\n")
        assert opens == closes, f"unbalanced COPY opens/closes in {part.name}"
