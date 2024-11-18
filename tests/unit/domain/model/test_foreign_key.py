"""ForeignKey is a frozen value object."""

from __future__ import annotations

import dataclasses

import pytest

from db2sql.domain.model import ForeignKey


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
