"""Pydantic schema for view exports."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from db2sql.application.dto import DataFormat
from db2sql.infrastructure.config import ColumnOverride, DumpConfig, ViewExport


def test_view_minimal_requires_only_a_query() -> None:
    cfg = DumpConfig(views={"summary": ViewExport(query="SELECT 1 AS one")})
    view = cfg.views["summary"]
    assert view.query == "SELECT 1 AS one"
    assert view.target_schema is None
    assert view.target_table is None
    assert view.data_format is None
    assert view.limit_records is None
    assert view.columns == {}
    assert view.primary_key == []
    assert view.indexes == {}


def test_view_full_carries_all_fields() -> None:
    cfg = DumpConfig(
        views={
            "customer_summary": ViewExport(
                query="SELECT id, total FROM stuff",
                target_schema="reporting",
                target_table="customer_totals",
                data_format=DataFormat.INSERT,
                limit_records=100,
                columns={"total": ColumnOverride(type="numeric", precision=10, scale=2)},
                primary_key=["id"],
                indexes={"idx_total": ["total"]},
            )
        }
    )
    view = cfg.views["customer_summary"]
    assert view.target_schema == "reporting"
    assert view.target_table == "customer_totals"
    assert view.data_format is DataFormat.INSERT
    assert view.limit_records == 100
    assert view.columns["total"].type == "numeric"
    assert view.columns["total"].precision == 10
    assert view.columns["total"].scale == 2
    assert view.primary_key == ["id"]
    assert view.indexes == {"idx_total": ["total"]}


def test_view_rejects_unknown_fields() -> None:
    with pytest.raises(ValidationError):
        ViewExport(query="SELECT 1", unknown_option=True)  # type: ignore[call-arg]


def test_column_override_rejects_unknown_fields() -> None:
    with pytest.raises(ValidationError):
        ColumnOverride(type="text", bogus=42)  # type: ignore[call-arg]


def test_view_query_is_required() -> None:
    with pytest.raises(ValidationError):
        ViewExport()  # type: ignore[call-arg]


def test_dump_config_views_defaults_to_empty_dict() -> None:
    assert DumpConfig().views == {}
