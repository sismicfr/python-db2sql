"""Filter policy: include/exclude logic and pure ``filter_database`` behaviour."""

from __future__ import annotations

import pytest

from db2sql.domain.model import Database, Schema, Table
from db2sql.domain.policy import FilterRules, filter_database


def _make_db() -> Database:
    db = Database(name="main")
    public = Schema(name="public")
    public.add_table(Table(name="author"))
    public.add_table(Table(name="book"))
    db.add_schema(public)
    private = Schema(name="private")
    private.add_table(Table(name="secret"))
    db.add_schema(private)
    return db


class TestFilterRules:
    def test_no_rules_includes_everything(self) -> None:
        rules = FilterRules()
        assert rules.table_included("public", "author") is True

    def test_exclude_schemas(self) -> None:
        rules = FilterRules(exclude_schemas=frozenset({"private"}))
        assert rules.table_included("public", "author") is True
        assert rules.table_included("private", "secret") is False

    def test_include_schemas_acts_as_allow_list(self) -> None:
        rules = FilterRules(include_schemas=frozenset({"public"}))
        assert rules.table_included("public", "author") is True
        assert rules.table_included("private", "secret") is False

    def test_exclude_tables_supports_bare_and_qualified_names(self) -> None:
        rules_bare = FilterRules(exclude_tables=frozenset({"book"}))
        assert rules_bare.table_included("public", "book") is False
        assert rules_bare.table_included("public", "author") is True

        rules_full = FilterRules(exclude_tables=frozenset({"public.book"}))
        assert rules_full.table_included("public", "book") is False
        assert rules_full.table_included("public", "author") is True

    def test_include_tables_acts_as_allow_list(self) -> None:
        rules = FilterRules(include_tables=frozenset({"book"}))
        assert rules.table_included("public", "book") is True
        assert rules.table_included("public", "author") is False

    def test_exclude_takes_precedence_over_include_for_schemas(self) -> None:
        rules = FilterRules(
            include_schemas=frozenset({"public"}),
            exclude_schemas=frozenset({"public"}),
        )
        assert rules.table_included("public", "x") is False


class TestFilterDatabase:
    def test_returns_a_deep_copy_and_does_not_mutate_source(self) -> None:
        source = _make_db()
        rules = FilterRules(exclude_tables=frozenset({"book"}))
        result = filter_database(source, rules)

        # source is intact
        assert "book" in source.schemas["public"].tables
        # result no longer contains book
        assert "book" not in result.schemas["public"].tables
        assert "author" in result.schemas["public"].tables
        # deep copy: same names but distinct objects
        assert result is not source
        assert result.schemas["public"] is not source.schemas["public"]

    def test_empty_schemas_are_pruned(self) -> None:
        source = _make_db()
        rules = FilterRules(exclude_tables=frozenset({"secret"}))
        result = filter_database(source, rules)
        assert "private" not in result.schemas
        assert "public" in result.schemas

    def test_include_only_keeps_listed_tables(self) -> None:
        source = _make_db()
        rules = FilterRules(include_tables=frozenset({"author"}))
        result = filter_database(source, rules)
        assert set(result.schemas) == {"public"}
        assert set(result.schemas["public"].tables) == {"author"}

    def test_no_rules_keeps_everything(self) -> None:
        source = _make_db()
        result = filter_database(source, FilterRules())
        assert set(result.schemas) == {"public", "private"}
        assert set(result.schemas["public"].tables) == {"author", "book"}
