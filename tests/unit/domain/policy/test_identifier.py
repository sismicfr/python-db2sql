"""Identifier-naming policy."""

from __future__ import annotations

import pytest

from db2sql.domain.policy import normalize_identifier, to_snake_case


@pytest.mark.parametrize(
    "name, expected",
    [
        ("CamelCase", "camel_case"),
        ("HTTPServer", "http_server"),
        ("already_snake", "already_snake"),
        ("lower", "lower"),
        ("Single", "single"),
        ("UserID", "user_id"),
        ("XMLParser", "xml_parser"),
        ("getHTTPResponseCode", "get_http_response_code"),
        ("MYTABLE", "mytable"),
        ("customer_ID", "customer_id"),
        ("", ""),
    ],
)
def test_to_snake_case(name: str, expected: str) -> None:
    assert to_snake_case(name) == expected


def test_to_snake_case_is_idempotent() -> None:
    once = to_snake_case("HTTPServerName")
    assert to_snake_case(once) == once


def test_normalize_identifier_preserve_case_returns_input() -> None:
    assert normalize_identifier("UserName", preserve_case=True) == "UserName"


def test_normalize_identifier_lowers_when_case_not_preserved() -> None:
    assert normalize_identifier("UserName", preserve_case=False) == "user_name"
