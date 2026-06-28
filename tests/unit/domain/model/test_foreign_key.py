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


def test_foreign_key_constraint_is_frozen() -> None:
    fkc = ForeignKeyConstraint(
        name="fk_test", ref_schema="s", ref_table="t",
        columns=("a",), ref_columns=("b",),
    )
    with pytest.raises(dataclasses.FrozenInstanceError):
        fkc.name = "other"  # type: ignore[misc]


def test_foreign_key_constraint_equality() -> None:
    a = ForeignKeyConstraint("fk", "s", "t", ("c1", "c2"), ("r1", "r2"))
    b = ForeignKeyConstraint("fk", "s", "t", ("c1", "c2"), ("r1", "r2"))
    c = ForeignKeyConstraint("fk", "s", "t", ("c1",), ("r1",))
    assert a == b
    assert a != c


def test_foreign_key_constraint_is_hashable() -> None:
    fkc = ForeignKeyConstraint("fk", "s", "t", ("c1",), ("r1",))
    assert {fkc: 1}[fkc] == 1
