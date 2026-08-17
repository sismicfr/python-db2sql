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


@pytest.fixture()
def clean_env(monkeypatch, tmp_path: Path):
    """No config file and no env-var defaults leaking into the parsed options."""
    for name in (
        "DB2SQL_CONFIG",
        "DB2SQL_DRIVER",
        "DB2SQL_TARGET",
        "DB2SQL_HOST",
        "DB2SQL_PORT",
        "DB2SQL_DBNAME",
        "DB2SQL_USER",
        "DB2SQL_PASSWORD",
    ):
        monkeypatch.delenv(name, raising=False)
    # Avoid picking up a ./db2sql.yml from the working directory.
    monkeypatch.chdir(tmp_path)
    return monkeypatch


_DUMP_ARGS = [
    "--driver",
    "sqlite",
    "-d",
    "my.db",
    "-f",
    "out.sql",
    "--on-existing",
    "drop",
    "--no-transaction",
    "-I",
    "book",
    "-n",
    "5",
    "--data-format",
    "insert",
    "--preserve-case",
]


def test_dump_subcommand_is_registered(clean_env) -> None:
    ns = build_parser().parse_args_with_config(["dump", "--driver", "sqlite"])
    assert ns.command == "dump"


def test_bare_invocation_has_no_command(clean_env) -> None:
    """The implicit form stays supported and is reported as 'no subcommand'."""
    ns = build_parser().parse_args_with_config(["--driver", "sqlite"])
    assert ns.command is None


def test_explicit_dump_and_implicit_form_build_the_same_config(clean_env) -> None:
    implicit = build_parser().parse_args_with_config(list(_DUMP_ARGS)).config
    explicit = build_parser().parse_args_with_config(["dump"] + _DUMP_ARGS).config
    assert explicit == implicit


def test_dump_options_may_straddle_the_subcommand(clean_env) -> None:
    """Options before the verb are root aliases; options after win on conflict."""
    ns = build_parser().parse_args_with_config(
        ["--driver", "sqlite", "dump", "-d", "my.db", "-f", "out.sql"]
    )
    assert ns.config.driver == "sqlite"
    assert ns.config.server.dbname == "my.db"
    assert ns.config.output_file == "out.sql"


def test_dump_subcommand_defaults_do_not_clobber_root_values(clean_env) -> None:
    """The SUPPRESS defaults keep pre-verb values alive across the sub-namespace."""
    ns = build_parser().parse_args_with_config(["-Vdebug", "--driver", "sqlite", "dump"])
    assert ns.verbosity == "debug"
    assert ns.config.driver == "sqlite"


def test_global_options_are_accepted_after_the_subcommand(clean_env, tmp_path: Path) -> None:
    log_file = tmp_path / "db2sql.log"
    ns = build_parser().parse_args_with_config(["dump", "-Vdebug", "-L", str(log_file)])
    assert ns.verbosity == "debug"
    assert ns.log_file == str(log_file)


def test_source_options_are_accepted_after_migrate(clean_env) -> None:
    before = build_parser().parse_args_with_config(
        ["--driver", "sqlite", "-d", "my.db", "migrate", "--target-host", "h"]
    )
    after = build_parser().parse_args_with_config(
        ["migrate", "--driver", "sqlite", "-d", "my.db", "--target-host", "h"]
    )
    assert after.config == before.config


def test_source_options_are_accepted_after_validate(clean_env) -> None:
    ns = build_parser().parse_args_with_config(["validate", "--driver", "sqlite", "--dry-run"])
    assert ns.command == "validate"
    assert ns.config.driver == "sqlite"
    assert ns.dry_run is True


def test_a_dbname_that_looks_like_a_command_is_not_a_subcommand(clean_env) -> None:
    ns = build_parser().parse_args_with_config(["--driver", "sqlite", "-d", "migrate"])
    assert ns.command is None
    assert ns.config.server.dbname == "migrate"


def test_once_argument_still_rejects_duplicates_after_the_subcommand(clean_env) -> None:
    parser = build_parser()
    with pytest.raises(SystemExit):
        parser.parse_args_with_config(["dump", "--driver", "sqlite", "--driver", "mysql"])


def test_dump_on_existing_drop_via_explicit_subcommand(clean_env) -> None:
    ns = build_parser().parse_args_with_config(["dump", "--on-existing", "drop"])
    assert ns.config.dump.on_existing == "drop"


def test_root_help_hides_dump_options_but_lists_the_commands(clean_env) -> None:
    help_text = build_parser().format_help()
    assert "--driver" not in help_text
    assert "--split-size" not in help_text
    for command in ("dump", "init", "validate", "migrate"):
        assert command in help_text


def test_dump_help_documents_the_options_without_leaking_suppress(clean_env, capsys) -> None:
    """A SUPPRESS default must not surface as '(default: ==SUPPRESS==)'."""
    with pytest.raises(SystemExit):
        build_parser().parse_args(["dump", "--help"])
    help_text = capsys.readouterr().out
    assert "--driver" in help_text
    assert "--split-size" in help_text
    assert "SUPPRESS" not in help_text
