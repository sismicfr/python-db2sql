"""Pydantic configuration schema: validators for the include/exclude lists."""

from __future__ import annotations

import pytest

from db2sql.infrastructure.config import DumpConfig, MigrateConfig


def test_none_becomes_empty_list() -> None:
    cfg = DumpConfig(include_schemas=None)  # type: ignore[arg-type]
    assert cfg.include_schemas == []


def test_string_input_is_split_on_commas() -> None:
    cfg = DumpConfig(include_schemas="public, private,  other")  # type: ignore[arg-type]
    assert cfg.include_schemas == ["public", "private", "other"]


def test_string_input_drops_empty_segments() -> None:
    cfg = DumpConfig(include_schemas=",  ,public,")  # type: ignore[arg-type]
    assert cfg.include_schemas == ["public"]


def test_list_with_int_elements_is_stringified() -> None:
    cfg = DumpConfig(include_schemas=[1, 2, "three"])  # type: ignore[arg-type]
    assert cfg.include_schemas == ["1", "2", "three"]


def test_list_of_strings_with_commas_is_re_split() -> None:
    cfg = DumpConfig(exclude_tables=["a,b", "c"])
    assert cfg.exclude_tables == ["a", "b", "c"]


def test_nested_list_is_flattened() -> None:
    cfg = DumpConfig(exclude_tables=[["a", "b"], ["c"]])  # type: ignore[arg-type]
    assert cfg.exclude_tables == ["a", "b", "c"]


def test_unexpected_input_type_is_passed_through() -> None:
    """Pydantic then rejects it, but the validator itself accepts arbitrary input."""
    with pytest.raises(Exception):
        DumpConfig(include_schemas=12345)  # type: ignore[arg-type]


def test_dump_on_existing_defaults_to_fail() -> None:
    assert DumpConfig().on_existing == "fail"


def test_dump_on_existing_accepts_drop() -> None:
    assert DumpConfig(on_existing="drop").on_existing == "drop"


def test_dump_on_existing_accepts_truncate() -> None:
    assert DumpConfig(on_existing="truncate").on_existing == "truncate"


def test_dump_on_existing_rejects_unknown_value() -> None:
    with pytest.raises(Exception):
        DumpConfig(on_existing="wipe")


def test_migrate_on_existing_accepts_all_three_values() -> None:
    for value in ("fail", "drop", "truncate"):
        assert MigrateConfig(on_existing=value).on_existing == value


def test_migrate_on_existing_rejects_unknown_value() -> None:
    with pytest.raises(Exception):
        MigrateConfig(on_existing="wipe")
