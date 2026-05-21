"""Interactive wizard that generates a db2sql configuration file."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

import questionary
import yaml
from pydantic import ValidationError

from db2sql.application.dto import DataFormat
from db2sql.infrastructure.config import AppConfig
from db2sql.infrastructure.config.errors import ConfigInvalidError
from db2sql.infrastructure.plugins import available_emitters, available_readers

from .exit_codes import ERROR_ENCOUNTERED, ERROR_INVALID_CONFIGURATION, SUCCESS

OutputFormat = str  # "yaml" or "json"

_DEFAULT_PORTS: Dict[str, int] = {
    "mssql": 1433,
    "mysql": 3306,
    "postgres": 5432,
    "oracle": 1521,
}

_DRIVERS_WITHOUT_AUTH = {"sqlite"}


class InitAborted(Exception):
    """User cancelled the wizard (Ctrl+C or declined the final confirmation)."""


class Prompter:
    """Abstraction over user prompts so tests can script the wizard."""

    def select(self, message: str, choices: List[str], default: Optional[str] = None) -> str:
        answer = questionary.select(message, choices=choices, default=default).ask()
        if answer is None:
            raise InitAborted()
        return str(answer)

    def text(
        self,
        message: str,
        default: str = "",
        validate: Optional[Callable[[str], Any]] = None,
    ) -> str:
        question = questionary.text(message, default=default, validate=validate)
        answer = question.ask()
        if answer is None:
            raise InitAborted()
        return str(answer)

    def password(self, message: str) -> str:
        answer = questionary.password(message).ask()
        if answer is None:
            raise InitAborted()
        return str(answer)

    def confirm(self, message: str, default: bool = False) -> bool:
        answer = questionary.confirm(message, default=default).ask()
        if answer is None:
            raise InitAborted()
        return bool(answer)

    def info(self, message: str) -> None:
        print(message, file=sys.stderr)


def _validate_required(value: str) -> Any:
    if not value or not value.strip():
        return "This field is required."
    return True


def _validate_int(value: str) -> Any:
    try:
        int(value)
    except ValueError:
        return "Please enter an integer."
    return True


def _parse_csv(value: str) -> List[str]:
    return [item.strip() for item in value.split(",") if item.strip()]


def _ask_csv_list(prompter: Prompter, message: str) -> List[str]:
    """Comma-separated input plus a loop allowing additional batches."""
    accumulated: List[str] = []
    while True:
        raw = prompter.text(message, default="")
        accumulated.extend(_parse_csv(raw))
        if not prompter.confirm("Add more entries?", default=False):
            break
    # de-duplicate while preserving order
    seen: set[str] = set()
    deduped: List[str] = []
    for item in accumulated:
        if item not in seen:
            seen.add(item)
            deduped.append(item)
    return deduped


def _ask_password(prompter: Prompter) -> Optional[str]:
    if not prompter.confirm("Store a password in the config file?", default=False):
        return None
    prompter.info("Note: the password will be written in plain text in the file.")
    while True:
        pw1 = prompter.password("Password")
        pw2 = prompter.password("Confirm password")
        if pw1 == pw2:
            return pw1
        prompter.info("Passwords do not match — please retry.")


def _ask_server(prompter: Prompter, driver: str) -> Dict[str, Any]:
    """Ask the connection questions appropriate for the given driver."""
    server: Dict[str, Any] = {}
    options: Dict[str, str] = {}

    if driver == "sqlite":
        server["dbname"] = prompter.text(
            "Path to the SQLite file",
            default="./myapp.sqlite",
            validate=_validate_required,
        )
        schema = prompter.text("Logical schema name", default="public")
        if schema:
            options["schema"] = schema
    elif driver == "oracle":
        server["hostname"] = prompter.text("Hostname", validate=_validate_required)
        port_default = str(_DEFAULT_PORTS.get(driver, 1521))
        server["port"] = int(prompter.text("Port", default=port_default, validate=_validate_int))
        server["username"] = prompter.text("Username", default="")
        mode = prompter.select(
            "Identify the database via",
            choices=["service_name", "sid"],
            default="service_name",
        )
        options[mode] = prompter.text(f"{mode}", validate=_validate_required)
        owner = prompter.text("Owner (schema) to dump, empty to dump everything", default="")
        if owner:
            options["owner"] = owner
        password = _ask_password(prompter)
        if password is not None:
            server["password"] = password
    else:
        # mssql / mysql / postgres / unknown network driver
        server["hostname"] = prompter.text("Hostname", validate=_validate_required)
        port_default = str(_DEFAULT_PORTS.get(driver, 0)) if driver in _DEFAULT_PORTS else ""
        server["port"] = int(prompter.text("Port", default=port_default, validate=_validate_int))
        server["dbname"] = prompter.text("Database name", validate=_validate_required)
        server["username"] = prompter.text("Username", default="")
        password = _ask_password(prompter)
        if password is not None:
            server["password"] = password

    if options:
        server["options"] = options
    return server


def _ask_data_format(prompter: Prompter, target: str) -> DataFormat:
    choice = prompter.select(
        "Default data format",
        choices=[fmt.value for fmt in DataFormat],
        default=DataFormat.COPY.value,
    )
    fmt = DataFormat(choice)
    if target == "mssql" and fmt == DataFormat.COPY:
        prompter.info(
            "MSSQL has no streaming COPY equivalent — the default data format "
            "will be downgraded to 'insert'."
        )
        fmt = DataFormat.INSERT
    return fmt


def _ask_mapping_schemas(prompter: Prompter) -> Dict[str, str]:
    mapping: Dict[str, str] = {}
    while prompter.confirm("Add a schema mapping (source → target)?", default=False):
        source = prompter.text("Source schema name", validate=_validate_required)
        target = prompter.text(f"Target schema name for '{source}'", validate=_validate_required)
        mapping[source] = target
    return mapping


def _ask_table_overrides(prompter: Prompter) -> Dict[str, Dict[str, Any]]:
    tables: Dict[str, Dict[str, Any]] = {}
    while prompter.confirm("Add an override for a specific table?", default=False):
        name = prompter.text("Table name (bare or schema.table)", validate=_validate_required)
        override: Dict[str, Any] = {}
        fmt_choice = prompter.select(
            f"data_format for '{name}'",
            choices=["(inherit)", DataFormat.COPY.value, DataFormat.INSERT.value],
            default="(inherit)",
        )
        if fmt_choice != "(inherit)":
            override["data_format"] = fmt_choice
        limit_raw = prompter.text(f"limit_records for '{name}' (empty = inherit)", default="")
        if limit_raw.strip():
            try:
                override["limit_records"] = int(limit_raw)
            except ValueError:
                prompter.info("Invalid integer — skipping limit_records for this table.")
        where = prompter.text(
            f"WHERE clause for '{name}' (without the WHERE keyword, empty for none)",
            default="",
        )
        if where.strip():
            override["where"] = where.strip()
        tables[name] = override
    return tables


def _ask_dump_section(prompter: Prompter, target: str) -> Tuple[Dict[str, Any], DataFormat]:
    dump: Dict[str, Any] = {}

    if prompter.confirm("Preserve identifier case?", default=False):
        dump["preserve_case"] = True

    limit_raw = prompter.text(
        "Global row limit per table (-1 for no limit)",
        default="-1",
        validate=_validate_int,
    )
    limit_records = int(limit_raw)
    if limit_records != -1:
        dump["limit_records"] = limit_records

    fmt = _ask_data_format(prompter, target)
    if fmt != DataFormat.COPY:
        dump["default_data_format"] = fmt.value

    include_schemas = _ask_csv_list(prompter, "Schemas to include (comma-separated, empty = all)")
    if include_schemas:
        dump["include_schemas"] = include_schemas
    exclude_schemas = _ask_csv_list(prompter, "Schemas to exclude (comma-separated)")
    if exclude_schemas:
        dump["exclude_schemas"] = exclude_schemas
    include_tables = _ask_csv_list(prompter, "Tables to include (comma-separated)")
    if include_tables:
        dump["include_tables"] = include_tables
    exclude_tables = _ask_csv_list(prompter, "Tables to exclude (comma-separated)")
    if exclude_tables:
        dump["exclude_tables"] = exclude_tables

    mapping = _ask_mapping_schemas(prompter)
    if mapping:
        dump["mapping_schemas"] = mapping

    tables = _ask_table_overrides(prompter)
    if tables:
        dump["tables"] = tables

    return dump, fmt


def build_config(prompter: Prompter) -> Tuple[AppConfig, OutputFormat]:
    """Run the wizard and return the assembled :class:`AppConfig`."""
    readers = available_readers()
    if not readers:
        raise InitAborted()
    emitters = available_emitters()
    if not emitters:
        raise InitAborted()

    output_format = prompter.select("Output format", choices=["yaml", "json"], default="yaml")

    driver = prompter.select(
        "Source database driver",
        choices=readers,
        default="mssql" if "mssql" in readers else readers[0],
    )
    target = prompter.select(
        "Target SQL dialect",
        choices=emitters,
        default="postgres" if "postgres" in emitters else emitters[0],
    )

    server = _ask_server(prompter, driver)
    dump, _fmt = _ask_dump_section(prompter, target)

    output_file = prompter.text("Default SQL output file (empty to write to stdout)", default="")

    data: Dict[str, Any] = {
        "driver": driver,
        "target": target,
        "server": server,
        "dump": dump,
    }
    if output_file.strip():
        data["output_file"] = output_file.strip()

    try:
        config = AppConfig.model_validate(data)
    except ValidationError as exc:
        raise ConfigInvalidError(f"Invalid configuration produced by wizard: {exc}") from exc

    return config, output_format


def serialize_config(config: AppConfig, output_format: OutputFormat) -> str:
    """Serialize ``config`` as YAML or JSON, omitting default values."""
    payload = config.model_dump(mode="json", exclude_defaults=True)
    if output_format == "json":
        return json.dumps(payload, indent=2, sort_keys=False) + "\n"
    rendered: str = yaml.safe_dump(payload, sort_keys=False, default_flow_style=False)
    return rendered


def _write_output(
    rendered: str,
    output_path: Optional[str],
    force: bool,
    prompter: Prompter,
) -> None:
    if not output_path:
        sys.stdout.write(rendered)
        return

    path = Path(output_path)
    if path.exists() and not force:
        if not prompter.confirm(f"File {path} already exists. Overwrite?", default=False):
            raise InitAborted()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(rendered, encoding="utf-8")
    prompter.info(f"Wrote configuration to {path}")


def run_init(
    options: argparse.Namespace,
    prompter: Optional[Prompter] = None,
) -> int:
    """Execute the wizard. Returns a CLI exit code."""
    actual_prompter: Prompter = prompter or Prompter()
    try:
        config, output_format = build_config(actual_prompter)
        rendered = serialize_config(config, output_format)
        _write_output(
            rendered,
            getattr(options, "init_output", None),
            bool(getattr(options, "init_force", False)),
            actual_prompter,
        )
    except InitAborted:
        actual_prompter.info("Aborted.")
        return ERROR_ENCOUNTERED
    except ConfigInvalidError as exc:
        actual_prompter.info(str(exc))
        return ERROR_INVALID_CONFIGURATION
    return SUCCESS


__all__ = [
    "InitAborted",
    "Prompter",
    "build_config",
    "run_init",
    "serialize_config",
]
