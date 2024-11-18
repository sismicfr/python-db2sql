"""Domain-level errors."""

from __future__ import annotations

import pytest

from db2sql.domain.errors import (
    DomainError,
    DuplicatedColumnError,
    DuplicatedItemError,
    DuplicatedSchemaError,
    DuplicatedTableError,
)


def test_domain_error_exposes_message() -> None:
    err = DomainError("boom")
    assert err.message == "boom"
    assert str(err) == "boom"


@pytest.mark.parametrize(
    "cls, expected",
    [
        (DuplicatedSchemaError, "foo schema already collected"),
        (DuplicatedTableError, "foo table already collected"),
        (DuplicatedColumnError, "foo column already collected"),
    ],
)
def test_duplicate_errors_format_message(cls: type, expected: str) -> None:
    err = cls("foo")
    assert err.message == expected
    assert isinstance(err, DuplicatedItemError)
    assert isinstance(err, DomainError)
