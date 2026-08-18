"""attach_foreign_keys: grouping catalog rows into named constraints."""

from __future__ import annotations

from db2sql.domain.model import Column, Database, Schema, Table
from db2sql.infrastructure.persistence.foreign_keys import (
    ForeignKeyColumn,
    attach_foreign_keys,
)


def _database() -> Database:
    db = Database(name="main")
    schema = Schema(name="public")

    parent = Table(name="parent")
    parent.add_column(Column(name="a", type="int"))
    parent.add_column(Column(name="b", type="int"))
    schema.add_table(parent)

    child = Table(name="child")
    child.add_column(Column(name="pa", type="int"))
    child.add_column(Column(name="pb", type="int"))
    schema.add_table(child)

    db.add_schema(schema)
    return db


def _row(constraint: str, column: str, ref_column: str) -> ForeignKeyColumn:
    return ForeignKeyColumn(
        constraint=constraint,
        schema="public",
        table="child",
        column=column,
        ref_schema="public",
        ref_table="parent",
        ref_column=ref_column,
    )


def test_single_column_constraint() -> None:
    db = _database()
    attach_foreign_keys(db, [_row("fk", "pa", "a")])

    (constraint,) = db.get_table("public", "child").foreign_key_constraints
    assert constraint.name == "fk"
    assert constraint.columns == ("pa",)
    assert constraint.ref_columns == ("a",)


def test_composite_constraint_keeps_row_order() -> None:
    db = _database()
    attach_foreign_keys(db, [_row("fk", "pa", "a"), _row("fk", "pb", "b")])

    (constraint,) = db.get_table("public", "child").foreign_key_constraints
    assert constraint.columns == ("pa", "pb")
    assert constraint.ref_columns == ("a", "b")


def test_distinct_constraints_are_not_merged() -> None:
    db = _database()
    attach_foreign_keys(db, [_row("fk1", "pa", "a"), _row("fk2", "pb", "b")])

    constraints = db.get_table("public", "child").foreign_key_constraints
    assert [c.name for c in constraints] == ["fk1", "fk2"]
    assert all(len(c.columns) == 1 for c in constraints)


def test_per_column_marker_is_set_for_the_ordering_policy() -> None:
    db = _database()
    attach_foreign_keys(db, [_row("fk", "pa", "a"), _row("fk", "pb", "b")])

    child = db.get_table("public", "child")
    assert child.get_column("pa").foreign_key.table == "parent"
    assert child.get_column("pb").foreign_key.column == "b"


def test_incomplete_composite_constraint_is_dropped() -> None:
    db = _database()
    # "gone" was filtered out of the model, so the constraint cannot be honoured.
    attach_foreign_keys(db, [_row("fk", "pa", "a"), _row("fk", "gone", "b")])

    assert db.get_table("public", "child").foreign_key_constraints == []


def test_unknown_table_is_ignored() -> None:
    db = _database()
    attach_foreign_keys(
        db,
        [
            ForeignKeyColumn(
                constraint="fk",
                schema="public",
                table="ghost",
                column="pa",
                ref_schema="public",
                ref_table="parent",
                ref_column="a",
            )
        ],
    )

    assert db.get_table("public", "child").foreign_key_constraints == []
