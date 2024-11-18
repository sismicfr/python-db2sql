"""validate subcommand: syntax check, --dry-run, --with-counts."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Iterator, Tuple

import pytest

from db2sql.application.ports import Logger
from db2sql.domain.model import Column, Database, Schema, Table
from db2sql.infrastructure.config import AppConfig
from db2sql.infrastructure.persistence.errors import SourceReaderError
from db2sql.infrastructure.plugins import register_reader
from db2sql.interface.cli import (
    ERROR_GENERAL,
    ERROR_INVALID_CONFIGURATION,
    SUCCESS,
    Cli,
    main,
)


class _DummyReader:
    """In-memory reader: one schema (``public``) with two tables."""

    raise_on_collect = False

    def __init__(self, config: AppConfig, logger: Logger) -> None:
        self.config = config
        self.logger = logger

    def collect_metadata(self) -> Database:
        if self.raise_on_collect:
            raise SourceReaderError("simulated failure")
        db = Database(name="main")
        public = Schema(name="public")
        for name in ("users", "orders"):
            t = Table(name=name)
            t.add_column(Column(name="id", type="integer"))
            public.add_table(t)
        db.add_schema(public)
        return db

    def iter_rows(
        self, schema: str, table: Table, limit: int = -1
    ) -> Iterator[Tuple[Any, ...]]:
        rows = [(1,), (2,), (3,)]
        for index, row in enumerate(rows):
            if 0 <= limit <= index:
                return
            yield row


@pytest.fixture(autouse=True)
def _register() -> Iterator[None]:
    register_reader("dummy-validate", _DummyReader)
    _DummyReader.raise_on_collect = False
    yield


def _write_config(tmp_path: Path, body: str) -> Path:
    path = tmp_path / "db2sql.yml"
    path.write_text(body)
    return path


def test_validate_syntax_only_succeeds(tmp_path: Path, monkeypatch, capsys) -> None:
    monkeypatch.delenv("DB2SQL_CONFIG", raising=False)
    cfg = _write_config(tmp_path, "driver: dummy-validate\n")
    rc = main(["validate", str(cfg)])
    out = capsys.readouterr().out
    assert rc == SUCCESS
    assert "[Configuration]" in out
    assert "driver" in out and "dummy-validate" in out
    assert "OK: configuration is valid" in out
    # syntax-only must NOT open the source
    assert "[Source connection]" not in out


def test_validate_unknown_driver_fails(tmp_path: Path, monkeypatch, capsys) -> None:
    monkeypatch.delenv("DB2SQL_CONFIG", raising=False)
    cfg = _write_config(tmp_path, "driver: nope-driver\n")
    rc = main(["validate", str(cfg)])
    err = capsys.readouterr().out
    assert rc == ERROR_INVALID_CONFIGURATION
    assert "unknown driver 'nope-driver'" in err


def test_validate_invalid_yaml_returns_error_code(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.delenv("DB2SQL_CONFIG", raising=False)
    cfg = _write_config(tmp_path, "bogus_key: 1\n")
    rc = main(["validate", str(cfg)])
    assert rc == ERROR_INVALID_CONFIGURATION


def test_validate_dry_run_lists_filtered_plan(
    tmp_path: Path, monkeypatch, capsys
) -> None:
    monkeypatch.delenv("DB2SQL_CONFIG", raising=False)
    cfg = _write_config(
        tmp_path,
        "driver: dummy-validate\n"
        "dump:\n"
        "  exclude_tables: [orders]\n",
    )
    rc = main(["validate", str(cfg), "--dry-run"])
    out = capsys.readouterr().out
    assert rc == SUCCESS
    assert "[Source connection]" in out
    assert "[Filtering]" in out
    assert "1/2 kept" in out  # 1 of 2 tables kept
    assert "[Plan]" in out
    assert "- users" in out
    assert "- orders" not in out
    assert "OK: dry-run completed" in out


def test_validate_dry_run_reports_reader_error(
    tmp_path: Path, monkeypatch, capsys
) -> None:
    monkeypatch.delenv("DB2SQL_CONFIG", raising=False)
    _DummyReader.raise_on_collect = True
    cfg = _write_config(tmp_path, "driver: dummy-validate\n")
    rc = main(["validate", str(cfg), "--dry-run"])
    out = capsys.readouterr().out
    assert rc == ERROR_GENERAL
    assert "source reader failed: simulated failure" in out


def test_validate_with_counts_implies_dry_run(
    tmp_path: Path, monkeypatch, capsys
) -> None:
    monkeypatch.delenv("DB2SQL_CONFIG", raising=False)
    cfg = _write_config(tmp_path, "driver: dummy-validate\n")
    rc = main(["validate", str(cfg), "--with-counts"])
    out = capsys.readouterr().out
    assert rc == SUCCESS
    # No count_rows on _DummyReader → falls back to iter_rows; reader yields 3.
    assert "count=3" in out
    # dry-run side-effects also visible
    assert "[Source connection]" in out


def test_validate_with_counts_prefers_count_rows_method(
    tmp_path: Path, monkeypatch, capsys
) -> None:
    """When the reader exposes count_rows, it is preferred over iter_rows."""

    class _CountingReader(_DummyReader):
        def count_rows(self, schema: str, table: Table) -> int:
            return 42_000  # arbitrary, distinct from iter_rows count

    register_reader("counting-reader", _CountingReader)
    monkeypatch.delenv("DB2SQL_CONFIG", raising=False)
    cfg = _write_config(tmp_path, "driver: counting-reader\n")
    rc = main(["validate", str(cfg), "--with-counts"])
    out = capsys.readouterr().out
    assert rc == SUCCESS
    assert "count=42000" in out


def test_validate_falls_back_to_config_lookup_when_no_positional(
    tmp_path: Path, monkeypatch, capsys
) -> None:
    """Without a positional arg, the usual config-file lookup applies."""
    cfg = _write_config(tmp_path, "driver: dummy-validate\n")
    monkeypatch.setenv("DB2SQL_CONFIG", str(cfg))
    rc = main(["validate"])
    out = capsys.readouterr().out
    assert rc == SUCCESS
    assert "OK: configuration is valid" in out
