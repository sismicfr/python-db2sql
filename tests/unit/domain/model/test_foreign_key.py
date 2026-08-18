"""ForeignKey and ForeignKeyConstraint are frozen value objects."""

from __future__ import annotations

import dataclasses

import pytest

from db2sql.domain.model import ForeignKey, ForeignKeyConstraint


def test_foreign_key_is_frozen() -> None:
    fk = ForeignKey(schema="s", table="t", column="c")
    with pytest.raises(dataclasses.FrozenInstanceError):
        fk.schema = "other"  # type: ignore[misc]


def test_equality_is_structural() -> None:
    assert ForeignKey("s", "t", "c") == ForeignKey("s", "t", "c")
    assert ForeignKey("s", "t", "c") != ForeignKey("s", "t", "d")


def test_foreign_key_is_hashable() -> None:
    fk = ForeignKey("s", "t", "c")
    assert {fk: 1}[fk] == 1


def test_constraint_is_frozen() -> None:
    fkc = ForeignKeyConstraint("fk", "s", "t", ("a",), ("b",))
    with pytest.raises(dataclasses.FrozenInstanceError):
        fkc.name = "other"  # type: ignore[misc]


def test_constraint_equality_is_structural() -> None:
    assert ForeignKeyConstraint("fk", "s", "t", ("a", "b"), ("x", "y")) == ForeignKeyConstraint(
        "fk", "s", "t", ("a", "b"), ("x", "y")
    )
    assert ForeignKeyConstraint("fk", "s", "t", ("a", "b"), ("x", "y")) != ForeignKeyConstraint(
        "fk", "s", "t", ("a",), ("x",)
    )


def test_constraint_is_hashable() -> None:
    fkc = ForeignKeyConstraint("fk", "s", "t", ("a",), ("b",))
    assert {fkc: 1}[fkc] == 1
