"""Cli runner: end-to-end behavior with stubbed plugins, exit-code mapping."""

from __future__ import annotations

import json
import io
from pathlib import Path
from typing import Any, Iterator, Tuple
from unittest.mock import patch

import pytest

from db2sql.application.ports import Logger
from db2sql.domain.errors import DomainError
from db2sql.domain.model import Column, Database, ForeignKey, Schema, Table
from db2sql.infrastructure.config import AppConfig
from db2sql.infrastructure.config.errors import ConfigError
from db2sql.infrastructure.persistence.errors import SourceReaderError
from db2sql.infrastructure.plugins import (
    UnknownReaderError,
    register_reader,
)
from db2sql.interface.cli import (
    ERROR_ENCOUNTERED,
    ERROR_GENERAL,
    ERROR_INVALID_CONFIGURATION,
    ERROR_UNEXPECTED,
    SUCCESS,
    AbortExecution,
    Cli,
    CommandLineError,
    main,
)


class _SilentReader:
    """In-memory reader yielding one schema with one table and one row."""

    def __init__(self, config: AppConfig, logger: Logger) -> None:
        self.config = config
        self.logger = logger

    def collect_metadata(self) -> Database:
        db = Database(name="main")
        public = Schema(name="public")
        t = Table(name="thing")
        t.add_column(Column(name="id", type="integer"))
        public.add_table(t)
        db.add_schema(public)
        return db

    def iter_rows(self, schema: str, table: Table, limit: int = -1) -> Iterator[Tuple[Any, ...]]:
        yield (1,)


@pytest.fixture(autouse=True)
def _register_silent_reader() -> Iterator[None]:
    register_reader("silent-reader", _SilentReader)
    yield


def test_cli_run_returns_success_with_output_file(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.delenv("DB2SQL_CONFIG", raising=False)
    output = tmp_path / "out.sql"
    rc = Cli().run(["--driver", "silent-reader", "-f", str(output)])
    assert rc == SUCCESS
    contents = output.read_text()
    assert contents.startswith("BEGIN;")
    assert "COMMIT;" in contents


def test_cli_run_with_version_aborts_with_zero(monkeypatch, capsys) -> None:
    monkeypatch.delenv("DB2SQL_CONFIG", raising=False)
    cli = Cli()
    with pytest.raises(AbortExecution) as exc:
        cli.run(["--driver", "silent-reader", "--version"])
    assert exc.value.exitcode == 0


def test_cli_run_with_ask_password(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.delenv("DB2SQL_CONFIG", raising=False)
    output = tmp_path / "out.sql"
    monkeypatch.setattr("db2sql.interface.cli.runner.getpass.getpass", lambda _prompt: "s3cret")
    Cli().run(["--driver", "silent-reader", "-W", "-f", str(output)])
    # Just exercising the branch: the run should still succeed
    assert output.exists()


def test_exit_code_from_known_exceptions() -> None:
    cli = Cli()
    assert cli.exit_code_from(None) == SUCCESS
    assert cli.exit_code_from(AbortExecution(0)) == SUCCESS
    assert cli.exit_code_from(AbortExecution(2)) == ERROR_ENCOUNTERED
    assert cli.exit_code_from(CommandLineError("oops")) == ERROR_UNEXPECTED
    assert cli.exit_code_from(ConfigError("bad")) == ERROR_INVALID_CONFIGURATION
    assert cli.exit_code_from(UnknownReaderError("foo", [])) == ERROR_INVALID_CONFIGURATION
    assert cli.exit_code_from(SourceReaderError("nope")) == ERROR_GENERAL
    assert cli.exit_code_from(DomainError("oops")) == ERROR_GENERAL


def test_exit_code_from_system_exit() -> None:
    cli = Cli()
    assert cli.exit_code_from(SystemExit(0)) == ERROR_ENCOUNTERED
    assert cli.exit_code_from(SystemExit(2)) == ERROR_ENCOUNTERED


def test_exit_code_from_unexpected_falls_through() -> None:
    cli = Cli()
    code = cli.exit_code_from(RuntimeError("kaboom"))
    assert code == ERROR_UNEXPECTED


def test_main_returns_success(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.delenv("DB2SQL_CONFIG", raising=False)
    output = tmp_path / "out.sql"
    rc = main(["--driver", "silent-reader", "-f", str(output)])
    assert rc == SUCCESS


def test_main_returns_invalid_configuration_for_unknown_reader(monkeypatch) -> None:
    monkeypatch.delenv("DB2SQL_CONFIG", raising=False)
    rc = main(["--driver", "no-such-driver"])
    assert rc == ERROR_INVALID_CONFIGURATION


def test_main_handles_version_with_success(monkeypatch) -> None:
    monkeypatch.delenv("DB2SQL_CONFIG", raising=False)
    rc = main(["--driver", "silent-reader", "--version"])
    assert rc == SUCCESS


def test_cli_run_re_raises_command_line_errors_for_bad_choice(monkeypatch) -> None:
    """An invalid CLI argument should propagate (argparse raises SystemExit)."""
    monkeypatch.delenv("DB2SQL_CONFIG", raising=False)
    with pytest.raises(SystemExit):
        Cli().run(["--data-format", "bogus", "--driver", "silent-reader"])


def test_main_handles_argparse_systemexit(monkeypatch) -> None:
    monkeypatch.delenv("DB2SQL_CONFIG", raising=False)
    rc = main(["--data-format", "bogus", "--driver", "silent-reader"])
    assert rc == ERROR_ENCOUNTERED


def test_main_uses_sys_argv_when_no_args(monkeypatch) -> None:
    """Default branch in ``main()``: pull arguments from ``sys.argv``."""
    import sys as _sys

    monkeypatch.delenv("DB2SQL_CONFIG", raising=False)
    monkeypatch.setattr(_sys, "argv", ["db2sql", "--driver", "silent-reader", "--version"])
    rc = main()
    assert rc == SUCCESS


def test_main_traceback_path_for_unexpected_exception(monkeypatch) -> None:
    """An unexpected exception inside ``Cli.run`` is mapped to ERROR_UNEXPECTED."""
    monkeypatch.delenv("DB2SQL_CONFIG", raising=False)

    # Inject a reader that raises an unexpected exception during collect_metadata
    class _BoomReader:
        def __init__(self, config, logger): ...
        def collect_metadata(self):  # pragma: no cover - replaced below
            raise RuntimeError("kaboom")

        def iter_rows(self, *args, **kwargs):
            yield  # pragma: no cover

    register_reader("boom-reader", _BoomReader)
    rc = main(["--driver", "boom-reader"])
    assert rc == ERROR_UNEXPECTED


def test_cli_logger_property_returns_console_logger(monkeypatch) -> None:
    from db2sql.infrastructure.logging import ConsoleLogger

    monkeypatch.delenv("DB2SQL_CONFIG", raising=False)
    cli = Cli()
    assert isinstance(cli.logger, ConsoleLogger)


def test_exit_code_from_unrepresentable_exception() -> None:
    """If ``str(exception)`` itself raises, ``exit_code_from`` falls back to ``repr``."""

    class _Hostile(Exception):
        def __str__(self) -> str:
            raise RuntimeError("can't stringify")

    cli = Cli()
    code = cli.exit_code_from(_Hostile())
    assert code == ERROR_UNEXPECTED


def test_runner_signal_handlers_can_be_invoked(monkeypatch) -> None:
    """The ``main`` helper registers signal handlers; verify they call ``sys.exit``."""
    import signal as _signal

    monkeypatch.delenv("DB2SQL_CONFIG", raising=False)
    # Trigger main once to install the handlers.
    main(["--driver", "silent-reader", "--version"])

    sigint_handler = _signal.getsignal(_signal.SIGINT)
    sigterm_handler = _signal.getsignal(_signal.SIGTERM)
    assert callable(sigint_handler)
    assert callable(sigterm_handler)

    with pytest.raises(SystemExit) as exc:
        sigint_handler(_signal.SIGINT, None)
    assert exc.value.code == 2

    with pytest.raises(SystemExit) as exc:
        sigterm_handler(_signal.SIGTERM, None)
    assert exc.value.code == 4


def test_cli_warns_when_a_dsn_overrides_a_host_from_the_config_file(
    tmp_path: Path, monkeypatch, capsys
) -> None:
    """Overriding a file across layers is legal — but must not happen silently."""
    monkeypatch.delenv("DB2SQL_CONFIG", raising=False)
    cfg = tmp_path / "db2sql.json"
    cfg.write_text(json.dumps({"server": {"hostname": "from-file", "dbname": "from-file"}}))
    output = tmp_path / "out.sql"

    rc = Cli().run(
        [
            "--driver",
            "silent-reader",
            "-C",
            str(cfg),
            "--source-dsn",
            "silent-reader://host/db",
            "-f",
            str(output),
        ]
    )

    assert rc == SUCCESS
    captured = capsys.readouterr().out
    assert "--source-dsn is set" in captured
    assert "hostname" in captured and "dbname" in captured


def test_cli_rejects_a_dsn_combined_with_flags_on_the_same_command_line(
    tmp_path: Path, monkeypatch
) -> None:
    """Same-layer contradiction is a mistake, not an override: fail loudly."""
    monkeypatch.delenv("DB2SQL_CONFIG", raising=False)
    with pytest.raises(ConfigError):
        Cli().run(
            [
                "--driver",
                "silent-reader",
                "--source-dsn",
                "silent-reader://host/db",
                "-H",
                "conflicting",
                "-f",
                str(tmp_path / "never.sql"),
            ]
        )


def test_cli_does_not_warn_without_a_dsn(tmp_path: Path, monkeypatch, capsys) -> None:
    monkeypatch.delenv("DB2SQL_CONFIG", raising=False)
    output = tmp_path / "out.sql"
    assert Cli().run(["--driver", "silent-reader", "-d", "db", "-f", str(output)]) == SUCCESS
    assert "--source-dsn is set" not in capsys.readouterr().out
