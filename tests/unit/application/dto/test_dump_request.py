"""DumpOptions resolution chain (per-table override → global default)."""

from __future__ import annotations

from db2sql.application.dto import DataFormat, DumpOptions, TableOption


def test_default_data_format_when_no_override() -> None:
    options = DumpOptions(default_data_format=DataFormat.COPY)
    assert options.resolve_data_format("public", "author") is DataFormat.COPY


def test_override_data_format_with_qualified_name_wins() -> None:
    options = DumpOptions(
        default_data_format=DataFormat.COPY,
        table_options={"public.book": TableOption(data_format=DataFormat.INSERT)},
    )
    assert options.resolve_data_format("public", "book") is DataFormat.INSERT
    assert options.resolve_data_format("public", "author") is DataFormat.COPY


def test_override_data_format_with_bare_name() -> None:
    options = DumpOptions(
        default_data_format=DataFormat.COPY,
        table_options={"book": TableOption(data_format=DataFormat.INSERT)},
    )
    assert options.resolve_data_format("public", "book") is DataFormat.INSERT


def test_qualified_override_beats_bare_override() -> None:
    options = DumpOptions(
        default_data_format=DataFormat.COPY,
        table_options={
            "book": TableOption(data_format=DataFormat.COPY),
            "public.book": TableOption(data_format=DataFormat.INSERT),
        },
    )
    assert options.resolve_data_format("public", "book") is DataFormat.INSERT


def test_resolve_limit_falls_back_to_global() -> None:
    options = DumpOptions(limit_records=100)
    assert options.resolve_limit("public", "author") == 100


def test_resolve_limit_uses_override_when_present() -> None:
    options = DumpOptions(
        limit_records=100,
        table_options={"public.book": TableOption(limit_records=5)},
    )
    assert options.resolve_limit("public", "book") == 5
    assert options.resolve_limit("public", "author") == 100


def test_resolve_limit_override_with_zero_is_respected() -> None:
    options = DumpOptions(
        limit_records=-1,
        table_options={"book": TableOption(limit_records=0)},
    )
    assert options.resolve_limit("public", "book") == 0
