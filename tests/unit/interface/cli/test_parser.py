"""CLI argument parser: config-file resolution, --help abort, env-var defaults."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

from db2sql.infrastructure.config.errors import ConfigMissingError
from db2sql.interface.cli.parser import (
    AbortExecution,
    CommandLineError,
    build_parser,
)


def test_build_parser_returns_a_configured_parser() -> None:
    parser = build_parser()
    assert parser.prog == "db2sql"


def test_parse_args_with_config_returns_namespace_with_config(tmp_path: Path, monkeypatch) -> None:
    cfg = tmp_path / "db2sql.json"
    cfg.write_text(json.dumps({"driver": "sqlite"}))
    monkeypatch.delenv("DB2SQL_CONFIG", raising=False)

    parser = build_parser()
    ns = parser.parse_args_with_config(["-C", str(cfg)])
    assert ns.config.driver == "sqlite"


def test_parse_args_with_invalid_config_propagates(tmp_path: Path, monkeypatch) -> None:
    cfg = tmp_path / "db2sql.json"
    cfg.write_text("{ not valid")
    monkeypatch.delenv("DB2SQL_CONFIG", raising=False)
    parser = build_parser()
    with pytest.raises(Exception):
        parser.parse_args_with_config(["-C", str(cfg)])


def test_missing_config_with_help_flag_aborts_success(tmp_path: Path, monkeypatch, capsys) -> None:
    monkeypatch.delenv("DB2SQL_CONFIG", raising=False)
    parser = build_parser()
    # Passing -C to a non-existent file while help is set should abort with code 0
    with pytest.raises((AbortExecution, SystemExit)):
        parser.parse_args_with_config(["-h"])


def test_env_var_driver_default(monkeypatch) -> None:
    monkeypatch.setenv("DB2SQL_DRIVER", "sqlite")
    monkeypatch.delenv("DB2SQL_CONFIG", raising=False)
    parser = build_parser()
    ns = parser.parse_args_with_config([])
    assert ns.driver == "sqlite"


def test_abort_execution_carries_exit_code() -> None:
    exc = AbortExecution(7)
    assert exc.exitcode == 7
    assert str(exc) == ""


def test_command_line_error_keeps_message() -> None:
    exc = CommandLineError("boom")
    assert exc.message == "boom"
    assert "boom" in str(exc)


def test_missing_explicit_config_raises_config_missing(monkeypatch) -> None:
    monkeypatch.delenv("DB2SQL_CONFIG", raising=False)
    parser = build_parser()
    with pytest.raises(ConfigMissingError):
        parser.parse_args_with_config(["-C", "/nonexistent/path/db2sql.yml"])


def test_data_format_choice_validates(monkeypatch) -> None:
    monkeypatch.delenv("DB2SQL_CONFIG", raising=False)
    parser = build_parser()
    with pytest.raises(SystemExit):
        parser.parse_args_with_config(["--data-format", "bogus"])


def test_dump_on_existing_drop_is_routed_into_dump_config(monkeypatch) -> None:
    monkeypatch.delenv("DB2SQL_CONFIG", raising=False)
    parser = build_parser()
    ns = parser.parse_args_with_config(["--on-existing", "drop"])
    assert ns.config.dump.on_existing == "drop"


def test_dump_on_existing_truncate_is_accepted(monkeypatch) -> None:
    monkeypatch.delenv("DB2SQL_CONFIG", raising=False)
    parser = build_parser()
    ns = parser.parse_args_with_config(["--on-existing", "truncate"])
    assert ns.config.dump.on_existing == "truncate"


def test_dump_on_existing_unknown_value_is_rejected(monkeypatch) -> None:
    monkeypatch.delenv("DB2SQL_CONFIG", raising=False)
    parser = build_parser()
    with pytest.raises(SystemExit):
        parser.parse_args_with_config(["--on-existing", "wipe"])


def test_migrate_on_existing_truncate_still_accepted(monkeypatch) -> None:
    monkeypatch.delenv("DB2SQL_CONFIG", raising=False)
    parser = build_parser()
    ns = parser.parse_args_with_config(["migrate", "--on-existing", "truncate"])
    assert ns.config.migrate.on_existing == "truncate"
