"""resolve_schema_name: exact entry, ``*`` catch-all, identity fallback."""

from __future__ import annotations

from db2sql.domain.policy import resolve_schema_name


def test_exact_entry_wins() -> None:
    assert resolve_schema_name({"dbo": "public"}, "dbo") == "public"


def test_unmapped_schema_keeps_its_name() -> None:
    assert resolve_schema_name({"dbo": "public"}, "sales") == "sales"


def test_wildcard_catches_unmapped_schemas() -> None:
    assert resolve_schema_name({"*": "target"}, "sales") == "target"


def test_exact_entry_takes_precedence_over_wildcard() -> None:
    mapping = {"dbo": "public", "*": "target"}
    assert resolve_schema_name(mapping, "dbo") == "public"
    assert resolve_schema_name(mapping, "sales") == "target"


def test_empty_mapping_is_identity() -> None:
    assert resolve_schema_name({}, "public") == "public"
