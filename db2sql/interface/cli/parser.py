"""CLI argument parser for db2sql."""

from __future__ import annotations

import argparse
import os
import sys
from typing import Any, Optional, Sequence

from db2sql import const
from db2sql.application.dto import DataFormat
from db2sql.infrastructure.config import (
    AppConfig,
    ConfigError,
    load_config,
    merge_cli_overrides,
)
from db2sql.infrastructure.plugins import (
    available_emitters,
    available_readers,
    available_writers,
)

from .boolean_action import BooleanAction
from .once_argument import OnceArgument
from .smart_formatter import SmartFormatter

COMMAND_INIT = "init"
COMMAND_VALIDATE = "validate"
COMMAND_MIGRATE = "migrate"


class AbortExecution(Exception):
    """Abort but with success the current execution."""

    def __init__(self, exitcode: int = 0) -> None:
        super().__init__("")
        self.exitcode = exitcode


class CommandLineError(Exception):
    """One command-line argument is not defined properly."""

    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message


class MsDumpToPGArgumentParser(argparse.ArgumentParser):
    """Builds an :class:`AppConfig` from CLI args + config file + env."""

    def parse_args_with_config(self, args: Optional[Sequence[str]] = None) -> argparse.Namespace:
        options = super().parse_args(args)

        if "help" in options and options.help:
            self.print_help()
            raise AbortExecution(0)

        # The init subcommand creates a config from scratch; do not load one.
        if getattr(options, "command", None) == COMMAND_INIT:
            options.config = AppConfig()
            return options

        # The validate subcommand accepts the config file as a positional arg;
        # let it win over -C / env / default lookup if provided.
        config_file = options.config_file
        if getattr(options, "command", None) == COMMAND_VALIDATE and getattr(
            options, "validate_config_file", None
        ):
            config_file = options.validate_config_file

        try:
            base = load_config(config_file)
        except ConfigError as exc:
            if "--help" in (args or sys.argv) or "-h" in (args or sys.argv):
                self.print_help()
                raise AbortExecution(0) from exc
            raise

        config: AppConfig = merge_cli_overrides(base, vars(options))
        options.config = config
        return options


_SIZE_SUFFIXES = {
    "": 1,
    "B": 1,
    "K": 1024,
    "KB": 1024,
    "M": 1024 * 1024,
    "MB": 1024 * 1024,
    "G": 1024 * 1024 * 1024,
    "GB": 1024 * 1024 * 1024,
}


def _parse_size(value: str) -> int:
    """Parse a byte size such as ``100M`` or ``1024`` into bytes."""
    raw = value.strip().upper()
    if not raw:
        raise argparse.ArgumentTypeError("size cannot be empty")
    for suffix in ("GB", "MB", "KB", "G", "M", "K", "B"):
        if raw.endswith(suffix):
            number = raw[: -len(suffix)].strip() or "0"
            multiplier = _SIZE_SUFFIXES[suffix]
            break
    else:
        number = raw
        multiplier = 1
    try:
        amount = float(number)
    except ValueError as exc:
        raise argparse.ArgumentTypeError(f"invalid size: {value!r}") from exc
    bytes_value = int(amount * multiplier)
    if bytes_value <= 0:
        raise argparse.ArgumentTypeError(f"size must be > 0, got {value!r}")
    return bytes_value


def _add_dump_options(parser: argparse.ArgumentParser) -> None:
    """Add the connection/dump options shared by the implicit dump command."""
    parser.add_argument(
        "--driver",
        dest="driver",
        metavar="NAME",
        type=str,
        default=os.getenv(const.ENV_DB2SQL_DRIVER),
        help=(
            "Source database driver. Built-in: "
            f"{', '.join(available_readers()) or '(none registered)'}. "
            f"[env var: {const.ENV_DB2SQL_DRIVER}]"
        ),
        action=OnceArgument,
    )
    parser.add_argument(
        "--target",
        dest="target",
        metavar="NAME",
        type=str,
        default=os.getenv(const.ENV_DB2SQL_TARGET),
        help=(
            "Target SQL dialect to emit. Built-in: "
            f"{', '.join(available_emitters()) or '(none registered)'}. "
            f"[env var: {const.ENV_DB2SQL_TARGET}] (default: postgres)"
        ),
        action=OnceArgument,
    )
    parser.add_argument(
        "-H",
        "--host",
        metavar="HOSTNAME",
        dest="hostname",
        type=str,
        help=f"Database server host name. [env var: {const.ENV_DB2SQL_HOST}]",
        default=os.getenv(const.ENV_DB2SQL_HOST),
        action=OnceArgument,
    )
    parser.add_argument(
        "-P",
        "--port",
        metavar="PORT",
        dest="port",
        type=int,
        help=f"Database server port. [env var: {const.ENV_DB2SQL_PORT}]",
        default=os.getenv(const.ENV_DB2SQL_PORT),
        action=OnceArgument,
    )
    parser.add_argument(
        "-d",
        "--dbname",
        metavar="DBNAME",
        dest="dbname",
        type=str,
        help=f"Database name to connect to. [env var: {const.ENV_DB2SQL_DBNAME}]",
        default=os.getenv(const.ENV_DB2SQL_DBNAME),
        action=OnceArgument,
    )
    parser.add_argument(
        "-u",
        "--username",
        metavar="USERNAME",
        dest="username",
        type=str,
        help=f"Database user name. [env var: {const.ENV_DB2SQL_USER}]",
        default=os.getenv(const.ENV_DB2SQL_USER),
        action=OnceArgument,
    )
    parser.add_argument(
        "-p",
        "--password",
        metavar="PASSWORD",
        dest="password",
        type=str,
        help=f"Database password. [env var: {const.ENV_DB2SQL_PASSWORD}]",
        default=os.getenv(const.ENV_DB2SQL_PASSWORD),
        action=OnceArgument,
    )
    parser.add_argument(
        "-W",
        "--ask-password",
        dest="ask_password",
        action="store_true",
        default=False,
        help="Force password prompt.",
    )
    parser.add_argument(
        "-f",
        "--file",
        metavar="PATH",
        dest="output_file_name",
        type=str,
        default=None,
        help="Output file. If not provided, script is printed to standard output.",
    )
    parser.add_argument(
        "--split-size",
        metavar="SIZE",
        dest="split_size",
        type=_parse_size,
        default=None,
        help=(
            "Split the dump into multiple files when the current file exceeds "
            "SIZE. Accepts a byte count or a suffixed value (K/M/G). Requires -f."
        ),
    )
    parser.add_argument(
        "--on-existing",
        dest="dump_on_existing",
        choices=["fail", "drop", "truncate"],
        default=None,
        help=(
            "Strategy when a target object already exists: 'fail' (default) "
            "emits CREATE only; 'drop' prepends a DROP TABLE IF EXISTS for "
            "every table in reverse-dependency order; 'truncate' emits a "
            "data-only script (TRUNCATE + reload, no DDL)."
        ),
    )
    parser.add_argument(
        "--preserve-case",
        dest="preserve_case",
        action=BooleanAction,
        default=None,
        help="Preserve identifier case. When disabled, names are converted to snake_case.",
    )
    parser.add_argument(
        "--transaction",
        dest="dump_use_transaction",
        action=BooleanAction,
        default=None,
        help=(
            "Wrap the dump in a transaction (BEGIN/COMMIT). Disable with "
            "--no-transaction when the SQL is consumed by a tool that manages "
            "its own transaction or when chunked replay is preferred."
        ),
    )
    parser.add_argument(
        "-n",
        "--max-records",
        dest="limit_records",
        type=int,
        default=None,
        help="Limit the number of rows from each table. -1 means no limit.",
    )
    parser.add_argument(
        "--data-format",
        dest="data_format",
        choices=[fmt.value for fmt in DataFormat],
        default=None,
        help="Default output format for table data: copy (faster) or insert.",
    )
    parser.add_argument(
        "-i",
        "--include-schemas",
        metavar="NAME",
        dest="include_schemas",
        type=str,
        action="append",
        nargs="+",
        default=None,
        help="Schema names to include during export (repeatable, comma separated).",
    )
    parser.add_argument(
        "-x",
        "--exclude-schemas",
        metavar="NAME",
        dest="exclude_schemas",
        type=str,
        action="append",
        nargs="+",
        default=None,
        help="Schema names to exclude during export (repeatable, comma separated).",
    )
    parser.add_argument(
        "-I",
        "--include-tables",
        metavar="NAME",
        dest="include_tables",
        type=str,
        action="append",
        nargs="+",
        default=None,
        help="Table names to include during export (repeatable, comma separated).",
    )
    parser.add_argument(
        "-X",
        "--exclude-tables",
        metavar="NAME",
        dest="exclude_tables",
        type=str,
        action="append",
        nargs="+",
        default=None,
        help="Table names to exclude during export (repeatable, comma separated).",
    )
    parser.add_argument(
        "-C",
        "--config-file",
        metavar="PATH",
        dest="config_file",
        type=str,
        help=f"Configuration file to use. [env var: {const.ENV_DB2SQL_CONFIG}]",
    )
    parser.add_argument(
        "-L",
        "--log-file",
        metavar="PATH",
        dest="log_file",
        type=str,
        help="Send log output to PATH instead of stdout.",
        action=OnceArgument,
    )
    parser.add_argument(
        "-V",
        "--verbosity",
        metavar="LEVEL",
        dest="verbosity",
        default="status",
        nargs="?",
        type=str,
        help=(
            "Level of detail of the output. Valid options from less verbose to "
            "more verbose: -Vquiet, -Verror, -Vwarning, -Vnotice, -Vstatus, "
            "-V or -Vverbose, -VV or -Vdebug, -VVV or -Vtrace"
        ),
    )
    parser.add_argument(
        "--version",
        dest="version",
        action="store_true",
        default=False,
        help="Output version information and exit.",
    )


def _add_validate_subparser(subparsers: Any) -> None:
    """Add the ``validate`` subcommand.

    By default the subcommand only parses the configuration file and validates
    it against the Pydantic schema. With ``--dry-run`` it additionally
    connects to the source database, applies filtering rules, and prints a
    plain-text summary of what would be exported — without producing any SQL.
    """
    validate_parser = subparsers.add_parser(
        COMMAND_VALIDATE,
        help="Validate a configuration file (optionally dry-run the dump).",
        description=(
            "Without options, parse and validate the configuration file and "
            "exit. With --dry-run, also open the source connection, collect "
            "metadata, apply include/exclude rules, and print a textual plan "
            "of what would be exported. No SQL is emitted in either mode."
        ),
        formatter_class=SmartFormatter,
    )
    validate_parser.add_argument(
        "validate_config_file",
        metavar="CONFIG_FILE",
        nargs="?",
        default=None,
        help=(
            "Path to the configuration file to validate. When omitted, the "
            "usual lookup applies: -C, then $DB2SQL_CONFIG, then "
            "./db2sql.yml, /etc/db2sql.yml, ~/db2sql.yml."
        ),
    )
    validate_parser.add_argument(
        "--dry-run",
        dest="dry_run",
        action="store_true",
        default=False,
        help=(
            "Run the dump pipeline without emitting SQL: connect to the source, "
            "collect metadata, apply filters, and print a textual plan."
        ),
    )
    validate_parser.add_argument(
        "--with-counts",
        dest="with_counts",
        action="store_true",
        default=False,
        help=(
            "Count rows per kept table during --dry-run. Implies --dry-run. "
            "May be slow on large tables — issues one SELECT per table."
        ),
    )


def _add_migrate_subparser(subparsers: Any) -> None:
    """Add the ``migrate`` subcommand that streams a source DB into a live target.

    All connection-related flags are prefixed ``--target-*`` to avoid clashing
    with the top-level (source) flags. The dialect of the target is selected
    via the existing ``--target`` flag (postgres, mssql, …) — same key that
    selects the :class:`SqlEmitter`, so dump and migrate stay aligned.
    """
    migrate_parser = subparsers.add_parser(
        COMMAND_MIGRATE,
        help="Stream source database into a live target database (no SQL file).",
        description=(
            "Read metadata and rows from the source database (defined by the "
            "top-level --driver/-H/-P/... flags) and apply them directly to a "
            "live target database. The DDL is produced by the same SqlEmitter "
            "used by the file dump, so the resulting target schema is "
            "byte-identical to what 'db2sql > dump.sql && psql -f dump.sql' "
            "would have produced."
        ),
        formatter_class=SmartFormatter,
    )
    migrate_parser.add_argument(
        "--target-driver",
        dest="target_driver",
        metavar="NAME",
        type=str,
        default=None,
        help=(
            "Target writer name (defaults to --target). Built-in: "
            f"{', '.join(available_writers()) or '(none registered)'}."
        ),
        action=OnceArgument,
    )
    migrate_parser.add_argument(
        "--target-host",
        dest="target_hostname",
        metavar="HOSTNAME",
        type=str,
        default=os.getenv(const.ENV_DB2SQL_TARGET_HOST),
        help=f"Target database host. [env var: {const.ENV_DB2SQL_TARGET_HOST}]",
        action=OnceArgument,
    )
    migrate_parser.add_argument(
        "--target-port",
        dest="target_port",
        metavar="PORT",
        type=int,
        default=os.getenv(const.ENV_DB2SQL_TARGET_PORT),
        help=f"Target database port. [env var: {const.ENV_DB2SQL_TARGET_PORT}]",
        action=OnceArgument,
    )
    migrate_parser.add_argument(
        "--target-dbname",
        dest="target_dbname",
        metavar="DBNAME",
        type=str,
        default=os.getenv(const.ENV_DB2SQL_TARGET_DBNAME),
        help=f"Target database name. [env var: {const.ENV_DB2SQL_TARGET_DBNAME}]",
        action=OnceArgument,
    )
    migrate_parser.add_argument(
        "--target-user",
        dest="target_username",
        metavar="USERNAME",
        type=str,
        default=os.getenv(const.ENV_DB2SQL_TARGET_USER),
        help=f"Target database user. [env var: {const.ENV_DB2SQL_TARGET_USER}]",
        action=OnceArgument,
    )
    migrate_parser.add_argument(
        "--target-password",
        dest="target_password",
        metavar="PASSWORD",
        type=str,
        default=os.getenv(const.ENV_DB2SQL_TARGET_PASSWORD),
        help=f"Target database password. [env var: {const.ENV_DB2SQL_TARGET_PASSWORD}]",
        action=OnceArgument,
    )
    migrate_parser.add_argument(
        "--on-existing",
        dest="on_existing",
        choices=["fail", "drop", "truncate"],
        default=None,
        help="Strategy when a target object already exists (default: fail).",
    )
    migrate_parser.add_argument(
        "--transaction-mode",
        dest="transaction_mode",
        choices=["single", "per_table"],
        default=None,
        help="Transaction granularity for the migration (default: single).",
    )
    migrate_parser.add_argument(
        "--batch-size",
        dest="batch_size",
        type=int,
        default=None,
        help="Number of rows per bulk-load batch (default: 1000).",
    )
    migrate_parser.add_argument(
        "--transaction",
        dest="use_transaction",
        action=BooleanAction,
        default=None,
        help=(
            "Wrap the emitted SQL in a transaction (BEGIN/COMMIT). Disable "
            "with --no-transaction to let the target driver auto-commit each "
            "statement."
        ),
    )


def _add_init_subparser(subparsers: Any) -> None:
    """Add the ``init`` subcommand that generates a config file via a wizard."""
    init_parser = subparsers.add_parser(
        COMMAND_INIT,
        help="Interactively generate a db2sql configuration file.",
        description=(
            "Walk through a series of questions to produce a YAML or JSON "
            "configuration file ready to be passed to db2sql via -C."
        ),
        formatter_class=SmartFormatter,
    )
    init_parser.add_argument(
        "-o",
        "--output",
        dest="init_output",
        metavar="PATH",
        type=str,
        default=None,
        help="Write the generated config to PATH (default: stdout).",
    )
    init_parser.add_argument(
        "--force",
        dest="init_force",
        action="store_true",
        default=False,
        help="Overwrite the output file without asking for confirmation.",
    )


def build_parser() -> MsDumpToPGArgumentParser:
    parser = MsDumpToPGArgumentParser(
        description=(
            "Dump any supported source database into a PostgreSQL or Microsoft "
            "SQL Server SQL file (selectable via --target)."
        ),
        prog="db2sql",
        formatter_class=SmartFormatter,
        add_help=True,
    )
    _add_dump_options(parser)

    subparsers = parser.add_subparsers(
        dest="command",
        title="Commands",
        metavar="COMMAND",
    )
    _add_init_subparser(subparsers)
    _add_validate_subparser(subparsers)
    _add_migrate_subparser(subparsers)

    return parser
