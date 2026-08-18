"""validate subcommand — check config syntax, optionally dry-run the pipeline.

Three modes layered on top of each other:

* default — load the config file and validate it against the Pydantic schema
  (driver name resolves, target name resolves). No network I/O.
* ``--dry-run`` — open the source connection, collect metadata, apply
  filtering rules, and print a textual plan of what would be exported.
* ``--with-counts`` — additionally count rows per kept table (one SELECT per
  table). Implies ``--dry-run``.

In every mode the command produces a human-readable summary on stdout via
the supplied :class:`ConsoleLogger` and exits with a status code, **never**
emitting SQL.
"""

from __future__ import annotations

import argparse
from typing import List

from db2sql.application.dto import DumpRequest
from db2sql.application.ports import SourceReader
from db2sql.domain.model import Database, Table
from db2sql.domain.policy import filter_database, resolve_schema_name
from db2sql.infrastructure.config import AppConfig, to_dump_request
from db2sql.infrastructure.logging import ConsoleLogger, Palette
from db2sql.infrastructure.persistence.errors import SourceReaderError
from db2sql.infrastructure.plugins import (
    available_emitters,
    available_readers,
    get_source_reader,
    UnknownReaderError,
)

from .exit_codes import ERROR_GENERAL, ERROR_INVALID_CONFIGURATION, SUCCESS


def run_validate(options: argparse.Namespace, logger: ConsoleLogger) -> int:
    """Entry point dispatched from :class:`db2sql.interface.cli.runner.Cli`."""
    config: AppConfig = options.config
    dry_run = bool(getattr(options, "dry_run", False))
    with_counts = bool(getattr(options, "with_counts", False))
    if with_counts:
        dry_run = True  # --with-counts implies --dry-run

    # Phase 1 — Pydantic validation already happened during parsing; if we are
    # here the YAML/JSON is syntactically valid. Verify plugin names too, since
    # they are not validated by the schema.
    _print_header(logger, "Configuration")
    _print_kv(logger, "driver", config.driver)
    _print_kv(logger, "target", config.target)
    _print_kv(logger, "output_file", config.output_file or "(stdout)")

    plugin_error = _check_plugin_names(config, logger)
    if plugin_error is not None:
        return plugin_error

    if not dry_run:
        logger.write_raw("OK: configuration is valid", color=Palette.BRIGHT_GREEN)
        return SUCCESS

    return _run_dry_run(config, logger, with_counts=with_counts)


# --------------------------------------------------------------------------- #
# Phase 1 — plugin name resolution                                            #
# --------------------------------------------------------------------------- #


def _check_plugin_names(config: AppConfig, logger: ConsoleLogger) -> int | None:
    """Verify that ``driver`` and ``target`` map to a registered plugin."""
    readers = available_readers()
    emitters = available_emitters()
    if config.driver not in readers:
        logger.error(
            f"unknown driver {config.driver!r}; known: " f"{', '.join(sorted(readers)) or '(none)'}"
        )
        return ERROR_INVALID_CONFIGURATION
    if config.target not in emitters:
        logger.error(
            f"unknown target {config.target!r}; known: "
            f"{', '.join(sorted(emitters)) or '(none)'}"
        )
        return ERROR_INVALID_CONFIGURATION
    return None


# --------------------------------------------------------------------------- #
# Phase 2 — dry-run                                                            #
# --------------------------------------------------------------------------- #


def _run_dry_run(config: AppConfig, logger: ConsoleLogger, *, with_counts: bool) -> int:
    request = to_dump_request(config)
    _print_header(logger, "Source connection")
    _print_connection(logger, config)

    try:
        reader = get_source_reader(config.driver, config, logger)
        raw = reader.collect_metadata()
    except SourceReaderError as exc:
        logger.error(f"source reader failed: {exc.message}")
        return ERROR_GENERAL
    except UnknownReaderError as exc:
        logger.error(str(exc))
        return ERROR_INVALID_CONFIGURATION

    filtered = filter_database(raw, request.filter_rules)
    _print_filter_summary(logger, raw, filtered)
    _print_plan(logger, filtered, request, reader, with_counts=with_counts)

    logger.write_raw(
        "OK: dry-run completed; no SQL was emitted.",
        color=Palette.BRIGHT_GREEN,
    )
    return SUCCESS


def _print_connection(logger: ConsoleLogger, config: AppConfig) -> None:
    server = config.server
    if server.hostname:
        loc = server.hostname
        if server.port:
            loc = f"{loc}:{server.port}"
        _print_kv(logger, "host", loc)
    if server.dbname:
        _print_kv(logger, "dbname", server.dbname)
    if server.username:
        _print_kv(logger, "username", server.username)
    if server.password:
        _print_kv(logger, "password", "***")
    if server.options:
        pretty = ", ".join(f"{k}={v}" for k, v in sorted(server.options.items()))
        _print_kv(logger, "options", pretty)


def _print_filter_summary(logger: ConsoleLogger, raw: Database, filtered: Database) -> None:
    _print_header(logger, "Filtering")
    total_schemas = len(raw.schemas)
    total_tables = sum(len(s.tables) for s in raw.schemas.values())
    kept_schemas = len(filtered.schemas)
    kept_tables = sum(len(s.tables) for s in filtered.schemas.values())
    _print_kv(logger, "schemas", f"{kept_schemas}/{total_schemas} kept")
    _print_kv(logger, "tables", f"{kept_tables}/{total_tables} kept")

    dropped = _dropped_tables(raw, filtered)
    if dropped:
        _print_kv(logger, "dropped", ", ".join(dropped))


def _dropped_tables(raw: Database, filtered: Database) -> List[str]:
    out: List[str] = []
    for schema_name, schema in raw.schemas.items():
        kept = filtered.schemas.get(schema_name)
        kept_names = set(kept.tables) if kept else set()
        for table_name in schema.tables:
            if table_name not in kept_names:
                out.append(f"{schema_name}.{table_name}")
    return out


def _print_plan(
    logger: ConsoleLogger,
    database: Database,
    request: DumpRequest,
    reader: SourceReader,
    *,
    with_counts: bool,
) -> None:
    if not database.schemas:
        _print_header(logger, "Plan")
        logger.info("(no tables would be exported)")
        return

    _print_header(logger, "Plan")
    options = request.options
    for schema_name, schema in database.schemas.items():
        mapped = resolve_schema_name(options.mapping_schemas, schema_name)
        suffix = "" if mapped == schema_name else f" → {mapped}"
        logger.info(f"schema {schema_name}{suffix}")
        for table_name in schema.tables:
            fmt = options.resolve_data_format(schema_name, table_name).value
            limit = options.resolve_limit(schema_name, table_name)
            limit_str = "all rows" if limit < 0 else f"≤ {limit} rows"
            count_str = ""
            if with_counts:
                count = _count_rows(reader, schema_name, schema.tables[table_name], limit, logger)
                count_str = f", count={count}"
            logger.info(f"  - {table_name} (format={fmt}, {limit_str}{count_str})")


def _count_rows(
    reader: SourceReader, schema: str, table: Table, limit: int, logger: ConsoleLogger
) -> str:
    """Return a row count for the table.

    Prefers an optional ``count_rows(schema, table) -> int`` method on the
    reader (cheap: ``SELECT COUNT(*)``). Falls back to consuming ``iter_rows``
    (honest but expensive). On error returns ``"?"`` and logs a warning.
    """
    counter = getattr(reader, "count_rows", None)
    try:
        if callable(counter):
            return str(counter(schema, table))
        total = 0
        for total, _ in enumerate(reader.iter_rows(schema, table, limit=limit), start=1):
            pass
        return str(total)
    except Exception as exc:  # pylint: disable=broad-exception-caught  # pragma: no cover
        logger.warning(f"could not count rows for {schema}.{getattr(table, 'name', '?')}: {exc}")
        return "?"


# --------------------------------------------------------------------------- #
# Formatting helpers                                                          #
# --------------------------------------------------------------------------- #


def _print_header(logger: ConsoleLogger, title: str) -> None:
    logger.write_raw(f"\n[{title}]", color=Palette.BRIGHT_WHITE)


def _print_kv(logger: ConsoleLogger, key: str, value: str) -> None:
    logger.write_raw(f"  {key:<14} {value}")
