"""CLI end-to-end test: run ``Cli().run`` against a SQLite DB and inspect the dump file."""

from __future__ import annotations

import sys
from pathlib import Path

from db2sql.interface.cli import Cli


def test_cli_main_end_to_end(sample_db: Path, tmp_path: Path, monkeypatch) -> None:
    output_file = tmp_path / "dump.sql"
    monkeypatch.setattr(sys, "argv", ["db2sql"])
    rc = Cli().run(
        [
            "--driver",
            "sqlite",
            "-d",
            str(sample_db),
            "--preserve-case",
            "-f",
            str(output_file),
        ]
    )
    assert rc == 0
    contents = output_file.read_text()
    assert "BEGIN;" in contents and "COMMIT;" in contents
    assert 'COPY "public"."book"' in contents


def test_cli_no_transaction_omits_begin_and_commit(
    sample_db: Path, tmp_path: Path, monkeypatch
) -> None:
    output_file = tmp_path / "dump.sql"
    monkeypatch.setattr(sys, "argv", ["db2sql"])
    rc = Cli().run(
        [
            "--driver",
            "sqlite",
            "-d",
            str(sample_db),
            "--preserve-case",
            "--no-transaction",
            "-f",
            str(output_file),
        ]
    )
    assert rc == 0
    contents = output_file.read_text()
    assert "BEGIN" not in contents
    assert "COMMIT" not in contents


def test_cli_target_mssql_end_to_end(sample_db: Path, tmp_path: Path, monkeypatch) -> None:
    output_file = tmp_path / "dump.sql"
    monkeypatch.setattr(sys, "argv", ["db2sql"])
    rc = Cli().run(
        [
            "--driver",
            "sqlite",
            "--target",
            "mssql",
            "-d",
            str(sample_db),
            "--preserve-case",
            "-f",
            str(output_file),
        ]
    )
    assert rc == 0
    contents = output_file.read_text()
    assert "BEGIN TRANSACTION;" in contents
    assert "COMMIT TRANSACTION;" in contents
    assert "IF NOT EXISTS (SELECT 1 FROM sys.schemas WHERE name = N'public')" in contents
    assert "EXEC('CREATE SCHEMA [public]')" in contents
    assert "CREATE TABLE [public].[book]" in contents
    assert "INSERT INTO [public].[book]" in contents
    # MSSQL output must not contain Postgres-only constructs
    assert "COPY " not in contents
    assert "serial" not in contents
