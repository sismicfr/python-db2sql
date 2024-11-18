"""Database aggregate root."""

from __future__ import annotations

import pytest

from db2sql.domain.errors import DuplicatedSchemaError
from db2sql.domain.model import Database, Schema, Table


def test_add_and_get_schema() -> None:
    db = Database(name="main")
    public = Schema(name="public")
    db.add_schema(public)
    assert db.get_schema("public") is public
    assert db.get_schema("missing") is None


def test_duplicated_schema_raises() -> None:
    db = Database(name="main")
    db.add_schema(Schema(name="public"))
    with pytest.raises(DuplicatedSchemaError):
        db.add_schema(Schema(name="public"))


def test_add_table_routes_to_schema() -> None:
    db = Database(name="main")
    db.add_schema(Schema(name="public"))
    users = Table(name="users")
    db.add_table("public", users)
    assert db.get_table("public", "users") is users


def test_add_table_silently_ignores_unknown_schema() -> None:
    db = Database(name="main")
    db.add_table("missing", Table(name="users"))
    assert db.get_table("missing", "users") is None


def test_get_table_returns_none_for_missing_schema_or_table() -> None:
    db = Database(name="main")
    db.add_schema(Schema(name="public"))
    assert db.get_table("public", "users") is None
    assert db.get_table("missing", "users") is None
