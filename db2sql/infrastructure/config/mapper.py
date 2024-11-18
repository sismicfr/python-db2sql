"""Map a Pydantic :class:`AppConfig` to application-level request DTOs."""

from __future__ import annotations

from db2sql.application.dto import (
    ColumnOverrideOption,
    DumpOptions,
    DumpRequest,
    MigrateRequest,
    OnExisting,
    TableOption,
    TransactionMode,
    ViewExportRequest,
)
from db2sql.domain.policy import FilterRules

from .schema import AppConfig, ViewExport

_DEFAULT_VIEW_SCHEMA = "public"


def to_dump_request(config: AppConfig) -> DumpRequest:
    """Translate the infrastructure config into a pure application request."""
    dump = config.dump
    options = DumpOptions(
        preserve_case=dump.preserve_case,
        limit_records=dump.limit_records,
        default_data_format=dump.default_data_format,
        mapping_schemas=dict(dump.mapping_schemas),
        table_options={
            key: TableOption(
                data_format=override.data_format,
                limit_records=override.limit_records,
            )
            for key, override in dump.tables.items()
        },
    )
    filter_rules = FilterRules(
        include_schemas=frozenset(dump.include_schemas),
        exclude_schemas=frozenset(dump.exclude_schemas),
        include_tables=frozenset(dump.include_tables),
        exclude_tables=frozenset(dump.exclude_tables),
    )
    views = tuple(_to_view_request(key, view) for key, view in dump.views.items())
    return DumpRequest(
        options=options,
        filter_rules=filter_rules,
        output_file=config.output_file,
        views=views,
        split_size=config.split_size,
        on_existing=OnExisting(dump.on_existing),
        use_transaction=dump.use_transaction,
    )


def to_migrate_request(config: AppConfig) -> MigrateRequest:
    """Translate the infrastructure config into a pure migration request.

    The dump-level :class:`DumpOptions`, :class:`FilterRules` and view requests
    are reused as-is so the DDL produced by the emitter is identical between
    dump and migrate paths.
    """
    base = to_dump_request(config)
    migrate_cfg = config.migrate
    return MigrateRequest(
        options=base.options,
        filter_rules=base.filter_rules,
        views=base.views,
        on_existing=OnExisting(migrate_cfg.on_existing),
        transaction_mode=TransactionMode(migrate_cfg.transaction_mode),
        batch_size=migrate_cfg.batch_size,
        use_transaction=migrate_cfg.use_transaction,
    )


def _to_view_request(key: str, view: ViewExport) -> ViewExportRequest:
    return ViewExportRequest(
        key=key,
        query=view.query,
        target_schema=view.target_schema or _DEFAULT_VIEW_SCHEMA,
        target_table=view.target_table or key,
        data_format=view.data_format,
        limit_records=view.limit_records,
        column_overrides={
            name: ColumnOverrideOption(
                type=override.type,
                nullable=override.nullable,
                char_length=override.char_length,
                precision=override.precision,
                scale=override.scale,
            )
            for name, override in view.columns.items()
        },
        primary_key=tuple(view.primary_key),
        indexes={name: tuple(cols) for name, cols in view.indexes.items()},
    )
