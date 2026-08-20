"""CLI end-to-end test: run ``Cli().run`` against a SQLite DB and inspect the dump file."""

from __future__ import annotations

import sqlite3
import sys
from pathlib import Path

from db2sql.interface.cli import Cli, main


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
    assert (
        'ALTER TABLE "public"."book" ADD FOREIGN KEY ("author_id") '
        'REFERENCES "public"."author" ("id");' in contents
    )


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


def test_cli_explicit_dump_command_matches_implicit_form(
    sample_db: Path, tmp_path: Path, monkeypatch
) -> None:
    """``db2sql dump ...`` must produce exactly what the bare form produces."""
    monkeypatch.setattr(sys, "argv", ["db2sql"])
    implicit_file = tmp_path / "implicit.sql"
    explicit_file = tmp_path / "explicit.sql"

    common = ["--driver", "sqlite", "-d", str(sample_db), "--preserve-case", "-f"]
    assert Cli().run(common + [str(implicit_file)]) == 0
    assert Cli().run(["dump"] + common + [str(explicit_file)]) == 0

    assert explicit_file.read_text() == implicit_file.read_text()


def test_cli_source_dsn_matches_the_discrete_connection_flags(
    sample_db: Path, tmp_path: Path, monkeypatch
) -> None:
    """A DSN must reach the very same database as -d does."""
    monkeypatch.setattr(sys, "argv", ["db2sql"])
    via_flags = tmp_path / "flags.sql"
    via_dsn = tmp_path / "dsn.sql"

    assert (
        Cli().run(["dump", "--driver", "sqlite", "-d", str(sample_db), "-f", str(via_flags)]) == 0
    )
    assert (
        Cli().run(
            [
                "dump",
                "--driver",
                "sqlite",
                "--source-dsn",
                f"sqlite:///{sample_db}",
                "-f",
                str(via_dsn),
            ]
        )
        == 0
    )

    assert via_dsn.read_text() == via_flags.read_text()


def test_cli_source_dsn_of_another_dialect_is_rejected(
    sample_db: Path, tmp_path: Path, monkeypatch
) -> None:
    """A postgres DSN handed to the sqlite driver must fail, not connect anyway."""
    monkeypatch.setattr(sys, "argv", ["db2sql"])
    output_file = tmp_path / "never.sql"
    rc = main(
        [
            "dump",
            "--driver",
            "sqlite",
            "--source-dsn",
            "postgresql://u:p@h/d",
            "-f",
            str(output_file),
        ]
    )
    assert rc != 0


def test_cli_dump_command_accepts_options_before_and_after_the_verb(
    sample_db: Path, tmp_path: Path, monkeypatch
) -> None:
    """Flags may sit on either side of ``dump`` — the root aliases still parse."""
    monkeypatch.setattr(sys, "argv", ["db2sql"])
    output_file = tmp_path / "dump.sql"
    rc = Cli().run(
        [
            "--driver",
            "sqlite",
            "dump",
            "-d",
            str(sample_db),
            "--preserve-case",
            "-f",
            str(output_file),
        ]
    )
    assert rc == 0
    assert 'COPY "public"."book"' in output_file.read_text()


def test_cli_emits_composite_foreign_key_as_one_statement(
    tmp_path: Path, monkeypatch
) -> None:
    """A two-column FK must stay one constraint.

    Emitted column by column, each half would reference a non-unique key and
    the target refuses the statement ("no unique constraint matching given
    keys for referenced table").
    """
    db_path = tmp_path / "composite.db"
    conn = sqlite3.connect(db_path)
    conn.executescript(
        """
        CREATE TABLE convoque (
            id INTEGER NOT NULL,
            state TEXT NOT NULL,
            name TEXT,
            PRIMARY KEY (id, state)
        );
        CREATE TABLE vote (
            id INTEGER PRIMARY KEY,
            convoque_id INTEGER NOT NULL,
            state TEXT NOT NULL,
            FOREIGN KEY (convoque_id, state) REFERENCES convoque(id, state)
        );
        """
    )
    conn.commit()
    conn.close()

    output_file = tmp_path / "dump.sql"
    monkeypatch.setattr(sys, "argv", ["db2sql"])
    rc = Cli().run(
        ["--driver", "sqlite", "-d", str(db_path), "--preserve-case", "-f", str(output_file)]
    )
    assert rc == 0
    contents = output_file.read_text()
    assert contents.count("ADD FOREIGN KEY") == 1
    assert 'ADD FOREIGN KEY ("convoque_id", "state")' in contents
    assert 'REFERENCES "public"."convoque" ("id", "state")' in contents
