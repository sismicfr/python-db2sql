"""Configuration file loading and CLI merge utilities."""

from __future__ import annotations

import os
from json import loads as load_json
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Union

from pydantic import ValidationError
from yaml import safe_load as load_yaml

from db2sql import const
from db2sql.domain.policy import WILDCARD

from .errors import (
    ConfigInvalidError,
    ConfigMissingError,
    ConfigUnsupportedFileExtensionError,
)
from .schema import AppConfig

PathLike = Union[str, Path]

_DEFAULT_CONFIG_FILES: List[str] = [
    "db2sql.yml",
    "/etc/db2sql.yml",
    str(Path.home() / "db2sql.yml"),
]

_SERVER_FIELDS = {"hostname", "port", "username", "password", "dbname", "dsn"}
_TARGET_SERVER_FIELDS = {
    "target_hostname",
    "target_port",
    "target_username",
    "target_password",
    "target_dbname",
    "target_dsn",
}
_MIGRATE_FIELDS = {"on_existing", "transaction_mode", "batch_size", "use_transaction"}
_DUMP_FIELDS = {
    "preserve_case",
    "limit_records",
    "default_data_format",
    "include_schemas",
    "exclude_schemas",
    "include_tables",
    "exclude_tables",
    "mapping_schemas",
    "tables",
}

# CLI flags on the implicit dump are renamed with a ``dump_`` prefix to avoid
# colliding with same-named flags on the migrate subparser (which may have
# different semantics, e.g. on-existing has different allowed choices).
_DUMP_ALIASES = {
    "dump_on_existing": "on_existing",
    "dump_use_transaction": "use_transaction",
}


def _resolve_file(filepath: PathLike) -> str:
    return str(Path(filepath).resolve(strict=True))


def _get_config_file(config_file: Optional[PathLike] = None) -> Optional[str]:
    """Resolve config-file precedence: explicit arg, env var, default locations."""
    if config_file:
        try:
            return _resolve_file(config_file)
        except OSError as exo:
            raise ConfigMissingError(f"Cannot read config from file: {config_file}") from exo

    env_config = os.environ.get(const.ENV_DB2SQL_CONFIG)
    if env_config:
        try:
            return _resolve_file(env_config)
        except OSError as exo:
            raise ConfigMissingError(
                f"Cannot read config from: {const.ENV_DB2SQL_CONFIG}: {exo}"
            ) from exo

    for default in _DEFAULT_CONFIG_FILES:
        try:
            return _resolve_file(default)
        except OSError:
            continue
    return None


def _load_file(file_path: str) -> Any:
    _, ext = os.path.splitext(file_path)
    with open(file_path, "r", encoding="utf-8") as stream:
        if ext in (".yml", ".yaml"):
            return load_yaml(stream)
        if ext == ".json":
            return load_json(stream.read())
    raise ConfigUnsupportedFileExtensionError(ext, file_path)


def load_config(config_file: Optional[PathLike] = None) -> AppConfig:
    """Load configuration from disk, returning an empty :class:`AppConfig` if no file."""
    resolved = _get_config_file(config_file)
    if resolved is None:
        return AppConfig()
    data = _load_file(resolved)
    if not data:
        return AppConfig()
    try:
        config = AppConfig.model_validate(data)
    except ValidationError as exc:
        raise ConfigInvalidError(f"Invalid configuration file {resolved}: {exc}") from exc
    _reject_dsn_conflicts(config, resolved)
    return config


def _reject_dsn_conflicts(config: AppConfig, source: str) -> None:
    """Refuse a ``dsn`` sitting next to discrete connection keys in the same file.

    A DSN replaces the connection rather than merging with it, so declaring
    both in one file states two contradictory intents. A DSN passed on the
    command line while the file describes a host is a different matter — that
    is the documented precedence, and the runner only warns about it.
    """
    for section in ("server", "target_server"):
        server = getattr(config, section)
        shadowed = server.fields_shadowed_by_dsn()
        if shadowed:
            keys = ", ".join(f"{section}.{name}" for name in shadowed)
            raise ConfigInvalidError(
                f"Invalid configuration file {source}: {section}.dsn cannot be combined "
                f"with {keys} — a DSN replaces the connection, it does not merge with it."
            )


def merge_cli_overrides(config: AppConfig, options: Mapping[str, Any]) -> AppConfig:
    """Apply non-``None`` CLI options on top of ``config`` and return a new object."""
    data: Dict[str, Any] = config.model_dump()
    server: Dict[str, Any] = data.get("server") or {}
    target_server: Dict[str, Any] = data.get("target_server") or {}
    dump: Dict[str, Any] = data.get("dump") or {}
    migrate: Dict[str, Any] = data.get("migrate") or {}

    for key, value in options.items():
        if value is None:
            continue
        if key in _SERVER_FIELDS:
            server[key] = value
        elif key in _TARGET_SERVER_FIELDS:
            target_server[key[len("target_") :]] = value
        elif key in _MIGRATE_FIELDS:
            migrate[key] = value
        elif key in _DUMP_FIELDS:
            dump[key] = value
        elif key in _DUMP_ALIASES:
            dump[_DUMP_ALIASES[key]] = value
        elif key == "driver":
            data["driver"] = value
        elif key == "target":
            data["target"] = value
        elif key == "data_format":
            dump["default_data_format"] = value
        elif key == "output_file_name":
            data["output_file"] = value
        elif key == "target_schema":
            # A catch-all entry, so per-schema entries from the config file keep
            # winning over the CLI flag.
            mapping = dict(dump.get("mapping_schemas") or {})
            mapping[WILDCARD] = value
            dump["mapping_schemas"] = mapping
        elif key == "split_size":
            data["split_size"] = value

    data["server"] = server
    data["target_server"] = target_server
    data["dump"] = dump
    data["migrate"] = migrate
    try:
        return AppConfig.model_validate(data)
    except ValidationError as exc:
        raise ConfigInvalidError(f"Invalid effective configuration: {exc}") from exc
