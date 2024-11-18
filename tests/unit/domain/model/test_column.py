"""Column entity."""

from __future__ import annotations

from db2sql.domain.model import Column, ForeignKey


def test_column_defaults() -> None:
    col = Column(name="id", type="integer")
    assert col.default is None
    assert col.nullable is False
    assert col.char_length == -1
    assert col.precision is None
    assert col.scale is None
    assert col.computed_definition is None
    assert col.identity is False
    assert col.constraint is None
    assert col.foreign_key is None
    assert col.is_primary_key is False


def test_column_is_primary_key_when_constraint_matches() -> None:
    col = Column(name="id", type="int", constraint="PRIMARY KEY")
    assert col.is_primary_key is True


def test_column_unique_constraint_not_primary_key() -> None:
    col = Column(name="email", type="text", constraint="UNIQUE")
    assert col.is_primary_key is False


def test_column_foreign_key_assignment() -> None:
    col = Column(name="author_id", type="int")
    col.foreign_key = ForeignKey("public", "author", "id")
    assert col.foreign_key is not None
    assert col.foreign_key.column == "id"
