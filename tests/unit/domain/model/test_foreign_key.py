"""ForeignKey is a frozen value object."""

from __future__ import annotations

import dataclasses

import pytest

from db2sql.domain.model import ForeignKey


def _fk(columns: tuple = ("author_id",), ref_columns: tuple = ("id",)) -> ForeignKey:
    return ForeignKey(schema="s", table="t", columns=columns, ref_columns=ref_columns)


def test_foreign_key_is_frozen() -> None:
    fk = _fk()
    with pytest.raises(dataclasses.FrozenInstanceError):
        fk.schema = "other"  # type: ignore[misc]


def test_equality_is_structural() -> None:
    assert _fk() == _fk()
    assert _fk() != _fk(ref_columns=("other",))


def test_foreign_key_is_hashable() -> None:
    fk = _fk()
    assert {fk: 1}[fk] == 1


def test_composite_key_keeps_column_order() -> None:
    fk = _fk(columns=("idagconvoque", "cetat"), ref_columns=("idagconvoque", "cetat"))
    assert fk.columns == ("idagconvoque", "cetat")
    assert fk.ref_columns == ("idagconvoque", "cetat")


def test_column_count_mismatch_is_rejected() -> None:
    with pytest.raises(ValueError):
        _fk(columns=("a", "b"), ref_columns=("id",))


def test_empty_key_is_rejected() -> None:
    with pytest.raises(ValueError):
        _fk(columns=(), ref_columns=())
