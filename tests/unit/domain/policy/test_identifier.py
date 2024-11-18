"""Identifier-naming policy."""

from __future__ import annotations

import pytest

from db2sql.domain.policy import normalize_identifier, to_snake_case


@pytest.mark.parametrize(
    "name, expected",
    [
        ("CamelCase", "camel_case"),
        ("HTTPServer", "h_t_t_p_server"),
        ("already_snake", "already_snake"),
        ("lower", "lower"),
        ("Single", "single"),
        ("UserID", "user_i_d"),
    ],
)
def test_to_snake_case(name: str, expected: str) -> None:
    assert to_snake_case(name) == expected


def test_normalize_identifier_preserve_case_returns_input() -> None:
    assert normalize_identifier("UserName", preserve_case=True) == "UserName"


def test_normalize_identifier_lowers_when_case_not_preserved() -> None:
    assert normalize_identifier("UserName", preserve_case=False) == "user_name"
