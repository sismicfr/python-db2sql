"""Table entity."""

from __future__ import annotations

import pytest

from db2sql.domain.errors import DuplicatedColumnError
from db2sql.domain.model import Column, Table


def _col(name: str, **kwargs: object) -> Column:
    return Column(name=name, type=str(kwargs.pop("type", "text")), **kwargs)  # type: ignore[arg-type]


def test_add_and_get_column() -> None:
    table = Table(name="users")
    col = _col("id", type="int")
    table.add_column(col)
    assert table.get_column("id") is col
    assert table.get_column("missing") is None


def test_duplicated_column_raises() -> None:
    table = Table(name="users")
    table.add_column(_col("id"))
    with pytest.raises(DuplicatedColumnError):
        table.add_column(_col("id"))


def test_add_index_accumulates_columns_in_order() -> None:
    table = Table(name="users")
    table.add_index("idx_name", "first")
    table.add_index("idx_name", "last")
    table.add_index("idx_email", "email")
    assert table.indexes == {"idx_name": ["first", "last"], "idx_email": ["email"]}


def test_primary_key_columns_preserves_insertion_order() -> None:
    table = Table(name="t")
    table.add_column(_col("a", constraint="PRIMARY KEY"))
    table.add_column(_col("b"))
    table.add_column(_col("c", constraint="PRIMARY KEY"))
    assert table.primary_key_columns() == ["a", "c"]


def test_primary_key_columns_empty_when_no_pk() -> None:
    table = Table(name="t")
    table.add_column(_col("a"))
    assert table.primary_key_columns() == []
