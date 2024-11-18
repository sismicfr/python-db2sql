"""Schema entity."""

from __future__ import annotations

import pytest

from db2sql.domain.errors import DuplicatedTableError
from db2sql.domain.model import Schema, Table


def test_add_and_get_table() -> None:
    schema = Schema(name="public")
    t = Table(name="users")
    schema.add_table(t)
    assert schema.get_table("users") is t
    assert schema.get_table("missing") is None


def test_duplicated_table_raises() -> None:
    schema = Schema(name="public")
    schema.add_table(Table(name="users"))
    with pytest.raises(DuplicatedTableError):
        schema.add_table(Table(name="users"))
