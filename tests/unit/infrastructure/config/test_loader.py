"""Config loader: file resolution and CLI override merging."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from db2sql.application.dto import DataFormat
from db2sql.infrastructure.config import (
    AppConfig,
    ConfigInvalidError,
    ConfigUnsupportedFileExtensionError,
    load_config,
    merge_cli_overrides,
)


def test_load_config_returns_defaults_when_no_file(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("DB2SQL_CONFIG", raising=False)
    config = load_config()
    assert isinstance(config, AppConfig)
    assert config.driver == "mssql"


def test_load_config_reads_json_file(tmp_path: Path) -> None:
    path = tmp_path / "config.json"
    path.write_text(json.dumps({"driver": "sqlite", "dump": {"preserve_case": True}}))
    config = load_config(path)
    assert config.driver == "sqlite"
    assert config.dump.preserve_case is True


def test_load_config_reads_yaml_file(tmp_path: Path) -> None:
    path = tmp_path / "config.yaml"
    path.write_text("driver: postgres\ndump:\n  preserve_case: true\n")
    config = load_config(path)
    assert config.driver == "postgres"
    assert config.dump.preserve_case is True


def test_unsupported_extension_raises(tmp_path: Path) -> None:
    path = tmp_path / "config.toml"
    path.write_text("driver = 'sqlite'\n")
    with pytest.raises(ConfigUnsupportedFileExtensionError):
        load_config(path)


def test_invalid_yaml_raises_config_invalid(tmp_path: Path) -> None:
    path = tmp_path / "bad.yaml"
    path.write_text("driver: 123\nunknown_field: nope\n")
    with pytest.raises(ConfigInvalidError):
        load_config(path)


class TestMergeCliOverrides:
    def test_none_values_do_not_override(self) -> None:
        base = AppConfig(driver="sqlite")
        merged = merge_cli_overrides(base, {"driver": None})
        assert merged.driver == "sqlite"

    def test_server_fields_are_routed_to_server(self) -> None:
        merged = merge_cli_overrides(
            AppConfig(),
            {"hostname": "db.example.com", "port": 5432, "username": "u"},
        )
        assert merged.server.hostname == "db.example.com"
        assert merged.server.port == 5432
        assert merged.server.username == "u"

    def test_dump_fields_are_routed_to_dump(self) -> None:
        merged = merge_cli_overrides(
            AppConfig(),
            {"preserve_case": True, "limit_records": 10},
        )
        assert merged.dump.preserve_case is True
        assert merged.dump.limit_records == 10

    def test_data_format_maps_to_default_data_format(self) -> None:
        merged = merge_cli_overrides(AppConfig(), {"data_format": "insert"})
        assert merged.dump.default_data_format is DataFormat.INSERT

    def test_output_file_name_maps_to_output_file(self) -> None:
        merged = merge_cli_overrides(AppConfig(), {"output_file_name": "/tmp/out.sql"})
        assert merged.output_file == "/tmp/out.sql"

    def test_driver_override_replaces_base(self) -> None:
        merged = merge_cli_overrides(AppConfig(driver="mssql"), {"driver": "sqlite"})
        assert merged.driver == "sqlite"

    def test_include_schemas_accepts_nested_lists_from_argparse(self) -> None:
        merged = merge_cli_overrides(
            AppConfig(), {"include_schemas": [["public", "private"], ["other"]]}
        )
        assert merged.dump.include_schemas == ["public", "private", "other"]

    def test_dump_use_transaction_alias_routes_to_dump(self) -> None:
        merged = merge_cli_overrides(AppConfig(), {"dump_use_transaction": False})
        assert merged.dump.use_transaction is False
        # Migrate side untouched.
        assert merged.migrate.use_transaction is True

    def test_migrate_use_transaction_routes_to_migrate(self) -> None:
        merged = merge_cli_overrides(AppConfig(), {"use_transaction": False})
        assert merged.migrate.use_transaction is False
        # Dump side untouched.
        assert merged.dump.use_transaction is True


def test_load_config_with_env_var_path(tmp_path: Path, monkeypatch) -> None:
    cfg = tmp_path / "from-env.yml"
    cfg.write_text("driver: postgres\n")
    monkeypatch.setenv("DB2SQL_CONFIG", str(cfg))
    config = load_config()
    assert config.driver == "postgres"


def test_load_config_env_var_missing_file_raises(tmp_path: Path, monkeypatch) -> None:
    from db2sql.infrastructure.config.errors import ConfigMissingError

    missing = tmp_path / "nope.yml"
    monkeypatch.setenv("DB2SQL_CONFIG", str(missing))
    with pytest.raises(ConfigMissingError):
        load_config()


def test_load_config_explicit_missing_file_raises(monkeypatch) -> None:
    from db2sql.infrastructure.config.errors import ConfigMissingError

    monkeypatch.delenv("DB2SQL_CONFIG", raising=False)
    with pytest.raises(ConfigMissingError):
        load_config("/this/path/does/not/exist.yml")


def test_load_config_empty_file_returns_defaults(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.delenv("DB2SQL_CONFIG", raising=False)
    empty = tmp_path / "empty.yml"
    empty.write_text("")
    config = load_config(empty)
    assert isinstance(config, AppConfig)
    assert config.driver == "mssql"


def test_merge_cli_overrides_reports_invalid_value() -> None:
    from db2sql.infrastructure.config.errors import ConfigInvalidError

    with pytest.raises(ConfigInvalidError):
        merge_cli_overrides(AppConfig(), {"port": "not-a-number"})


def test_unsupported_extension_error_carries_path(tmp_path: Path) -> None:
    from db2sql.infrastructure.config.errors import ConfigUnsupportedFileExtensionError

    err = ConfigUnsupportedFileExtensionError(".toml", str(tmp_path / "x.toml"))
    assert ".toml" in err.message
    assert "x.toml" in err.message


def test_config_file_rejects_dsn_next_to_discrete_server_keys(tmp_path: Path) -> None:
    """Declaring both in one file states two contradictory intents."""
    cfg = tmp_path / "db2sql.yml"
    cfg.write_text(
        "driver: postgres\n" "server:\n" "  dsn: postgresql://u:p@h/db\n" "  hostname: elsewhere\n"
    )
    with pytest.raises(ConfigInvalidError, match=r"server\.dsn cannot be combined"):
        load_config(cfg)


def test_config_file_rejects_dsn_next_to_discrete_target_keys(tmp_path: Path) -> None:
    cfg = tmp_path / "db2sql.yml"
    cfg.write_text(
        "driver: postgres\n"
        "target_server:\n"
        "  dsn: postgresql://u:p@h/db\n"
        "  dbname: elsewhere\n"
    )
    with pytest.raises(ConfigInvalidError, match=r"target_server\.dsn cannot be combined"):
        load_config(cfg)


def test_config_file_accepts_a_dsn_on_its_own(tmp_path: Path) -> None:
    cfg = tmp_path / "db2sql.yml"
    cfg.write_text("driver: postgres\nserver:\n  dsn: postgresql://u:p@h/db\n")
    assert load_config(cfg).server.dsn == "postgresql://u:p@h/db"


def test_config_file_accepts_a_dsn_next_to_non_connection_keys(tmp_path: Path) -> None:
    """options describe what to export, not how to connect — no conflict."""
    cfg = tmp_path / "db2sql.yml"
    cfg.write_text(
        "driver: oracle\n"
        "server:\n"
        "  dsn: oracle+oracledb://u:p@h:1521/?service_name=PDB1\n"
        "  options:\n"
        "    owner: HR\n"
    )
    config = load_config(cfg)
    assert config.server.options == {"owner": "HR"}
