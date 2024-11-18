"""AppConfig → DumpRequest mapping for the views feature."""

from __future__ import annotations

from db2sql.application.dto import DataFormat
from db2sql.infrastructure.config import (
    AppConfig,
    ColumnOverride,
    DumpConfig,
    ViewExport,
    to_dump_request,
)


def test_no_views_yields_empty_tuple() -> None:
    request = to_dump_request(AppConfig())
    assert request.views == ()


def test_view_target_schema_defaults_to_public() -> None:
    config = AppConfig(dump=DumpConfig(views={"summary": ViewExport(query="SELECT 1")}))
    request = to_dump_request(config)
    assert request.views[0].target_schema == "public"


def test_view_target_table_defaults_to_dict_key() -> None:
    config = AppConfig(dump=DumpConfig(views={"summary": ViewExport(query="SELECT 1")}))
    request = to_dump_request(config)
    assert request.views[0].target_table == "summary"


def test_explicit_target_schema_and_table_take_precedence() -> None:
    config = AppConfig(
        dump=DumpConfig(
            views={
                "k": ViewExport(
                    query="SELECT 1",
                    target_schema="reporting",
                    target_table="totals",
                )
            }
        )
    )
    view = to_dump_request(config).views[0]
    assert view.target_schema == "reporting"
    assert view.target_table == "totals"


def test_column_overrides_and_pk_and_indexes_are_carried() -> None:
    config = AppConfig(
        dump=DumpConfig(
            views={
                "k": ViewExport(
                    query="SELECT id, total FROM whatever",
                    data_format=DataFormat.INSERT,
                    limit_records=7,
                    columns={
                        "total": ColumnOverride(type="numeric", precision=10, scale=2)
                    },
                    primary_key=["id"],
                    indexes={"by_total": ["total"]},
                )
            }
        )
    )
    view = to_dump_request(config).views[0]
    assert view.key == "k"
    assert view.data_format is DataFormat.INSERT
    assert view.limit_records == 7
    assert view.column_overrides["total"].type == "numeric"
    assert view.column_overrides["total"].precision == 10
    assert view.primary_key == ("id",)
    assert view.indexes == {"by_total": ("total",)}


def test_multiple_views_are_translated_in_iteration_order() -> None:
    config = AppConfig(
        dump=DumpConfig(
            views={
                "first": ViewExport(query="SELECT 1"),
                "second": ViewExport(query="SELECT 2"),
            }
        )
    )
    keys = [v.key for v in to_dump_request(config).views]
    assert keys == ["first", "second"]
