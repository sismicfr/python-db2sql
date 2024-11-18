"""Tests for the ``db2sql init`` interactive wizard."""

from __future__ import annotations

import io
import json
from argparse import Namespace
from pathlib import Path
from typing import Any, List, Optional

import pytest
import yaml

from db2sql.application.dto import DataFormat
from db2sql.infrastructure.config import AppConfig
from db2sql.interface.cli.exit_codes import (
    ERROR_ENCOUNTERED,
    ERROR_INVALID_CONFIGURATION,
    SUCCESS,
)
from db2sql.interface.cli.init_command import (
    InitAborted,
    Prompter,
    _ask_csv_list,
    _ask_data_format,
    _ask_mapping_schemas,
    _ask_password,
    _ask_server,
    _ask_table_overrides,
    _parse_csv,
    _validate_int,
    _validate_required,
    build_config,
    run_init,
    serialize_config,
)


class ScriptedPrompter(Prompter):
    """Test prompter that returns scripted answers in order."""

    def __init__(self, answers: List[Any]) -> None:
        self.answers: List[Any] = list(answers)
        self.info_messages: List[str] = []
        self.history: List[tuple] = []

    def _pop(self, kind: str, message: str) -> Any:
        if not self.answers:
            raise AssertionError(
                f"No more scripted answers for {kind!r}: {message!r}"
            )
        value = self.answers.pop(0)
        self.history.append((kind, message, value))
        return value

    def select(
        self, message: str, choices: List[str], default: Optional[str] = None
    ) -> str:
        return str(self._pop("select", message))

    def text(
        self,
        message: str,
        default: str = "",
        validate: Any = None,
    ) -> str:
        return str(self._pop("text", message))

    def password(self, message: str) -> str:
        return str(self._pop("password", message))

    def confirm(self, message: str, default: bool = False) -> bool:
        return bool(self._pop("confirm", message))

    def info(self, message: str) -> None:
        self.info_messages.append(message)


# ----- Helpers ----------------------------------------------------------------


def test_validate_required_rejects_blank() -> None:
    assert _validate_required("") != True  # noqa: E712
    assert _validate_required("   ") != True  # noqa: E712
    assert _validate_required("abc") is True


def test_validate_int_accepts_integers_only() -> None:
    assert _validate_int("42") is True
    assert _validate_int("-1") is True
    assert _validate_int("foo") != True  # noqa: E712


def test_parse_csv_strips_and_skips_empty() -> None:
    assert _parse_csv("  a, b ,, c") == ["a", "b", "c"]
    assert _parse_csv("") == []


def test_ask_csv_list_accumulates_and_dedupes() -> None:
    p = ScriptedPrompter(
        [
            "a, b",       # text
            True,         # add more?
            "b, c",       # text
            False,        # add more?
        ]
    )
    assert _ask_csv_list(p, "msg") == ["a", "b", "c"]


def test_ask_csv_list_empty_input() -> None:
    p = ScriptedPrompter(["", False])
    assert _ask_csv_list(p, "msg") == []


# ----- Password flow ----------------------------------------------------------


def test_ask_password_skipped_when_declined() -> None:
    p = ScriptedPrompter([False])
    assert _ask_password(p) is None


def test_ask_password_double_entry_match() -> None:
    p = ScriptedPrompter([True, "s3cr3t", "s3cr3t"])
    assert _ask_password(p) == "s3cr3t"
    assert any("plain text" in m for m in p.info_messages)


def test_ask_password_retries_on_mismatch() -> None:
    p = ScriptedPrompter(
        [
            True,
            "pw1",
            "different",
            "pw2",
            "pw2",
        ]
    )
    assert _ask_password(p) == "pw2"
    assert any("not match" in m for m in p.info_messages)


# ----- Server (driver-conditional) -------------------------------------------


def test_ask_server_sqlite_uses_options_schema() -> None:
    p = ScriptedPrompter(["./db.sqlite", "app"])
    server = _ask_server(p, "sqlite")
    assert server == {"dbname": "./db.sqlite", "options": {"schema": "app"}}


def test_ask_server_sqlite_blank_schema_drops_options() -> None:
    p = ScriptedPrompter(["./db.sqlite", ""])
    server = _ask_server(p, "sqlite")
    assert "options" not in server


def test_ask_server_oracle_with_service_name_and_owner() -> None:
    p = ScriptedPrompter(
        [
            "oracle.example.com",  # hostname
            "1521",                 # port
            "admin",                # username
            "service_name",         # select
            "ORCLPDB1",             # service_name value
            "HR",                   # owner
            False,                  # password? no
        ]
    )
    server = _ask_server(p, "oracle")
    assert server["hostname"] == "oracle.example.com"
    assert server["port"] == 1521
    assert server["username"] == "admin"
    assert server["options"] == {"service_name": "ORCLPDB1", "owner": "HR"}
    assert "password" not in server


def test_ask_server_oracle_with_sid_no_owner_with_password() -> None:
    p = ScriptedPrompter(
        [
            "oracle.example.com",
            "1521",
            "admin",
            "sid",
            "ORCL",
            "",         # no owner
            True,       # password?
            "s3cr3t",
            "s3cr3t",
        ]
    )
    server = _ask_server(p, "oracle")
    assert server["options"] == {"sid": "ORCL"}
    assert server["password"] == "s3cr3t"


def test_ask_server_network_driver_default_port() -> None:
    p = ScriptedPrompter(
        [
            "pg.example.com",
            "5432",
            "mydb",
            "app",
            False,
        ]
    )
    server = _ask_server(p, "postgres")
    assert server["port"] == 5432
    assert server["dbname"] == "mydb"


# ----- Data format ------------------------------------------------------------


def test_ask_data_format_returns_user_choice() -> None:
    p = ScriptedPrompter(["insert"])
    assert _ask_data_format(p, "postgres") == DataFormat.INSERT


def test_ask_data_format_mssql_downgrades_copy_to_insert() -> None:
    p = ScriptedPrompter(["copy"])
    fmt = _ask_data_format(p, "mssql")
    assert fmt == DataFormat.INSERT
    assert any("downgraded" in m or "COPY" in m for m in p.info_messages)


# ----- Mapping schemas --------------------------------------------------------


def test_ask_mapping_schemas_loop() -> None:
    p = ScriptedPrompter(
        [
            True, "dbo", "public",
            True, "legacy", "archive",
            False,
        ]
    )
    assert _ask_mapping_schemas(p) == {"dbo": "public", "legacy": "archive"}


def test_ask_mapping_schemas_no_entries() -> None:
    p = ScriptedPrompter([False])
    assert _ask_mapping_schemas(p) == {}


# ----- Per-table overrides ----------------------------------------------------


def test_ask_table_overrides_full_entry() -> None:
    p = ScriptedPrompter(
        [
            True,                   # add table?
            "orders",               # name
            "insert",               # data_format
            "5000",                 # limit_records
            "status = 'active'",    # where
            False,                  # add another?
        ]
    )
    overrides = _ask_table_overrides(p)
    assert overrides == {
        "orders": {
            "data_format": "insert",
            "limit_records": 5000,
            "where": "status = 'active'",
        }
    }


def test_ask_table_overrides_inherit_skips_keys() -> None:
    p = ScriptedPrompter(
        [
            True,
            "orders",
            "(inherit)",  # data_format inherited
            "",           # limit inherited
            "",           # no where
            False,
        ]
    )
    assert _ask_table_overrides(p) == {"orders": {}}


def test_ask_table_overrides_invalid_limit_warns_and_skips() -> None:
    p = ScriptedPrompter(
        [
            True,
            "orders",
            "(inherit)",
            "not-a-number",
            "",
            False,
        ]
    )
    overrides = _ask_table_overrides(p)
    assert overrides == {"orders": {}}
    assert any("Invalid integer" in m for m in p.info_messages)


# ----- build_config end-to-end -----------------------------------------------


def _minimal_sqlite_answers() -> List[Any]:
    return [
        "yaml",            # output format
        "sqlite",          # driver
        "postgres",        # target
        "./db.sqlite",     # dbname
        "public",          # schema
        False,             # preserve case
        "-1",              # limit_records
        "copy",            # data format
        "", False,         # include_schemas
        "", False,         # exclude_schemas
        "", False,         # include_tables
        "", False,         # exclude_tables
        False,             # mapping_schemas
        False,             # per-table
        "",                # output_file
    ]


def test_build_config_minimal_sqlite_yields_minimal_yaml() -> None:
    p = ScriptedPrompter(_minimal_sqlite_answers())
    config, fmt = build_config(p)
    assert fmt == "yaml"
    assert isinstance(config, AppConfig)
    assert config.driver == "sqlite"
    assert config.target == "postgres"
    rendered = serialize_config(config, fmt)
    data = yaml.safe_load(rendered)
    # Defaults must be excluded.
    assert "target" not in data
    assert data["driver"] == "sqlite"
    assert data["server"]["dbname"] == "./db.sqlite"


def test_build_config_json_output() -> None:
    answers = _minimal_sqlite_answers()
    answers[0] = "json"
    p = ScriptedPrompter(answers)
    config, fmt = build_config(p)
    assert fmt == "json"
    rendered = serialize_config(config, fmt)
    parsed = json.loads(rendered)
    assert parsed["driver"] == "sqlite"


def test_build_config_with_output_file_and_lists() -> None:
    answers = [
        "yaml",
        "sqlite",
        "postgres",
        "./db.sqlite",
        "public",
        False,
        "-1",
        "copy",
        "", False,
        "", False,
        "", False,
        "audit_log, sessions", False,
        False,
        False,
        "dump.sql",
    ]
    p = ScriptedPrompter(answers)
    config, _ = build_config(p)
    assert config.output_file == "dump.sql"
    assert config.dump.exclude_tables == ["audit_log", "sessions"]


# ----- serialize_config -------------------------------------------------------


def test_serialize_config_yaml_excludes_defaults() -> None:
    config = AppConfig(driver="sqlite")
    rendered = serialize_config(config, "yaml")
    data = yaml.safe_load(rendered)
    assert data == {"driver": "sqlite"}


def test_serialize_config_json_excludes_defaults() -> None:
    config = AppConfig(driver="sqlite")
    rendered = serialize_config(config, "json")
    assert json.loads(rendered) == {"driver": "sqlite"}


# ----- run_init: file output, overwrite confirmation -------------------------


def test_run_init_stdout_when_no_output_path(monkeypatch, capsys) -> None:
    p = ScriptedPrompter(_minimal_sqlite_answers())
    monkeypatch.setattr(
        "db2sql.interface.cli.init_command.Prompter",
        lambda: p,
    )
    options = Namespace(init_output=None, init_force=False)
    rc = run_init(options, prompter=p)
    assert rc == SUCCESS
    captured = capsys.readouterr()
    data = yaml.safe_load(captured.out)
    assert data["driver"] == "sqlite"


def test_run_init_writes_file(tmp_path: Path) -> None:
    target = tmp_path / "db2sql.yml"
    p = ScriptedPrompter(_minimal_sqlite_answers())
    options = Namespace(init_output=str(target), init_force=False)
    rc = run_init(options, prompter=p)
    assert rc == SUCCESS
    assert target.exists()
    data = yaml.safe_load(target.read_text())
    assert data["driver"] == "sqlite"


def test_run_init_refuses_overwrite_unless_confirmed(tmp_path: Path) -> None:
    target = tmp_path / "db2sql.yml"
    target.write_text("pre-existing\n")
    answers = _minimal_sqlite_answers() + [False]  # decline overwrite
    p = ScriptedPrompter(answers)
    options = Namespace(init_output=str(target), init_force=False)
    rc = run_init(options, prompter=p)
    assert rc == ERROR_ENCOUNTERED
    assert target.read_text() == "pre-existing\n"


def test_run_init_overwrites_when_confirmed(tmp_path: Path) -> None:
    target = tmp_path / "db2sql.yml"
    target.write_text("pre-existing\n")
    answers = _minimal_sqlite_answers() + [True]  # accept overwrite
    p = ScriptedPrompter(answers)
    options = Namespace(init_output=str(target), init_force=False)
    rc = run_init(options, prompter=p)
    assert rc == SUCCESS
    content = target.read_text()
    assert "pre-existing" not in content
    assert "driver: sqlite" in content


def test_run_init_force_bypasses_overwrite_confirmation(tmp_path: Path) -> None:
    target = tmp_path / "db2sql.yml"
    target.write_text("pre-existing\n")
    p = ScriptedPrompter(_minimal_sqlite_answers())  # no overwrite prompt expected
    options = Namespace(init_output=str(target), init_force=True)
    rc = run_init(options, prompter=p)
    assert rc == SUCCESS
    assert "driver: sqlite" in target.read_text()


def test_run_init_aborted_returns_encountered_code() -> None:
    class AbortingPrompter(Prompter):
        def select(self, *_a, **_kw):
            raise InitAborted()

        def text(self, *_a, **_kw):  # pragma: no cover - never reached
            raise InitAborted()

        def password(self, *_a, **_kw):  # pragma: no cover
            raise InitAborted()

        def confirm(self, *_a, **_kw):  # pragma: no cover
            raise InitAborted()

        def info(self, _message):
            pass

    options = Namespace(init_output=None, init_force=False)
    rc = run_init(options, prompter=AbortingPrompter())
    assert rc == ERROR_ENCOUNTERED


# ----- run_init via runner ----------------------------------------------------


def test_runner_dispatches_init_subcommand(tmp_path: Path, monkeypatch) -> None:
    """End-to-end: ``db2sql init -o PATH`` triggers the wizard."""
    from db2sql.interface.cli import init_command
    from db2sql.interface.cli.runner import Cli

    captured: dict = {}

    def fake_run_init(options, prompter=None):
        captured["init_output"] = options.init_output
        captured["init_force"] = options.init_force
        return SUCCESS

    monkeypatch.setattr("db2sql.interface.cli.runner.run_init", fake_run_init)
    rc = Cli().run(["init", "-o", str(tmp_path / "out.yml"), "--force"])
    assert rc == SUCCESS
    assert captured["init_output"] == str(tmp_path / "out.yml")
    assert captured["init_force"] is True
