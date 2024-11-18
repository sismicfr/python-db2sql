"""Topological ordering of tables based on foreign-key dependencies."""

from __future__ import annotations

from db2sql.domain.model import Column, Database, ForeignKey, Schema, Table
from db2sql.domain.policy import drop_order, topological_order


def _table_with_fk(name: str, ref_schema: str, ref_table: str) -> Table:
    table = Table(name=name)
    table.add_column(
        Column(name=f"{ref_table}_id", type="int",
               foreign_key=ForeignKey(schema=ref_schema, table=ref_table, column="id"))
    )
    return table


def _make_db_parent_child() -> Database:
    db = Database(name="main")
    public = Schema(name="public")
    public.add_table(Table(name="parent"))
    public.add_table(_table_with_fk("child", "public", "parent"))
    db.add_schema(public)
    return db


class TestTopologicalOrder:
    def test_empty_database_returns_empty_list(self) -> None:
        assert topological_order(Database(name="main")) == []

    def test_parent_comes_before_child(self) -> None:
        order = topological_order(_make_db_parent_child())
        assert order.index(("public", "parent")) < order.index(("public", "child"))
        assert len(order) == 2

    def test_self_referencing_fk_does_not_block(self) -> None:
        db = Database(name="main")
        schema = Schema(name="public")
        schema.add_table(
            _table_with_fk("category", "public", "category")
        )
        db.add_schema(schema)
        assert topological_order(db) == [("public", "category")]

    def test_cycle_between_two_tables_returns_all_nodes(self) -> None:
        db = Database(name="main")
        schema = Schema(name="public")
        schema.add_table(_table_with_fk("a", "public", "b"))
        schema.add_table(_table_with_fk("b", "public", "a"))
        db.add_schema(schema)
        order = topological_order(db)
        assert set(order) == {("public", "a"), ("public", "b")}

    def test_fk_to_unknown_table_is_ignored(self) -> None:
        db = Database(name="main")
        schema = Schema(name="public")
        schema.add_table(_table_with_fk("orphan", "public", "missing"))
        db.add_schema(schema)
        assert topological_order(db) == [("public", "orphan")]

    def test_cross_schema_fk(self) -> None:
        db = Database(name="main")
        ref = Schema(name="ref")
        ref.add_table(Table(name="country"))
        main = Schema(name="main")
        main.add_table(_table_with_fk("user", "ref", "country"))
        db.add_schema(ref)
        db.add_schema(main)
        order = topological_order(db)
        assert order.index(("ref", "country")) < order.index(("main", "user"))


class TestDropOrder:
    def test_drop_order_is_reverse_of_topological(self) -> None:
        db = _make_db_parent_child()
        assert drop_order(db) == list(reversed(topological_order(db)))

    def test_drop_order_child_before_parent(self) -> None:
        order = drop_order(_make_db_parent_child())
        assert order.index(("public", "child")) < order.index(("public", "parent"))
