"""AppConfig → DumpRequest mapping."""

from __future__ import annotations

from db2sql.application.dto import DataFormat
from db2sql.infrastructure.config import (
    AppConfig,
    DumpConfig,
    MigrateConfig,
    ServerConfig,
    TableOverride,
    to_dump_request,
    to_migrate_request,
)


def test_default_app_config_maps_to_default_request() -> None:
    request = to_dump_request(AppConfig())
    assert request.options.preserve_case is False
    assert request.options.limit_records == -1
    assert request.options.default_data_format is DataFormat.COPY
    assert request.options.mapping_schemas == {}
    assert request.options.table_options == {}
    assert request.filter_rules.include_schemas == frozenset()
    assert request.filter_rules.exclude_schemas == frozenset()
    assert request.output_file is None


def test_filter_lists_become_frozensets() -> None:
    config = AppConfig(
        dump=DumpConfig(
            include_schemas=["public"],
            exclude_schemas=["private"],
            include_tables=["author"],
            exclude_tables=["book"],
        )
    )
    request = to_dump_request(config)
    assert request.filter_rules.include_schemas == frozenset({"public"})
    assert request.filter_rules.exclude_schemas == frozenset({"private"})
    assert request.filter_rules.include_tables == frozenset({"author"})
    assert request.filter_rules.exclude_tables == frozenset({"book"})


def test_table_overrides_are_carried_over() -> None:
    config = AppConfig(
        dump=DumpConfig(
            tables={
                "public.book": TableOverride(
                    data_format=DataFormat.INSERT, limit_records=10
                )
            }
        )
    )
    request = to_dump_request(config)
    override = request.options.table_options["public.book"]
    assert override.data_format is DataFormat.INSERT
    assert override.limit_records == 10


def test_mapping_schemas_and_output_file_are_carried_over() -> None:
    config = AppConfig(
        output_file="/tmp/out.sql",
        dump=DumpConfig(mapping_schemas={"dbo": "public"}),
    )
    request = to_dump_request(config)
    assert request.output_file == "/tmp/out.sql"
    assert request.options.mapping_schemas == {"dbo": "public"}


def test_use_transaction_default_is_true_for_dump_and_migrate() -> None:
    config = AppConfig()
    assert to_dump_request(config).use_transaction is True
    assert to_migrate_request(config).use_transaction is True


def test_use_transaction_false_is_propagated() -> None:
    config = AppConfig(
        dump=DumpConfig(use_transaction=False),
        migrate=MigrateConfig(use_transaction=False),
    )
    assert to_dump_request(config).use_transaction is False
    assert to_migrate_request(config).use_transaction is False


def test_server_config_does_not_leak_into_request() -> None:
    """``DumpRequest`` is for dump options only — connection info stays in AppConfig."""
    config = AppConfig(server=ServerConfig(hostname="db.example.com", password="secret"))
    request = to_dump_request(config)
    assert not hasattr(request, "server")
    assert not hasattr(request.options, "password")
