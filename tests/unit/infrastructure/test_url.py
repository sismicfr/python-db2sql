"""Shared SQLAlchemy URL builder: escaping, shape, and password redaction."""

from __future__ import annotations

import pytest
from sqlalchemy.engine import make_url

from db2sql.infrastructure.config import ConfigInvalidError, ServerConfig
from db2sql.infrastructure.url import build_url, database_from_url, redact_url


def test_build_url_full_shape() -> None:
    server = ServerConfig(hostname="h", port=5432, username="u", password="p", dbname="d")
    assert build_url(server, "postgresql+psycopg2") == "postgresql+psycopg2://u:p@h:5432/d"


def test_build_url_omits_port_when_missing() -> None:
    server = ServerConfig(hostname="h", username="u", password="p", dbname="d")
    assert build_url(server, "mysql+pymysql") == "mysql+pymysql://u:p@h/d"


def test_build_url_without_credentials_yields_file_url() -> None:
    server = ServerConfig(dbname="/tmp/x.db")
    url = build_url(server, "sqlite", database="/tmp/x.db", credentials=False)
    assert url == "sqlite:////tmp/x.db"


def test_build_url_appends_query_parameters() -> None:
    server = ServerConfig(hostname="db.local", port=1521, username="hr", password="pw")
    url = build_url(server, "oracle+oracledb", database="", query={"service_name": "ORCLPDB1"})
    assert url == "oracle+oracledb://hr:pw@db.local:1521/?service_name=ORCLPDB1"


@pytest.mark.parametrize("password", ["p@ss", "a/b", "a:b", "a b", "%40", "p#1?2"])
def test_credentials_survive_a_round_trip_through_sqlalchemy(password: str) -> None:
    """Special characters must not corrupt the URL — this used to break."""
    server = ServerConfig(hostname="h", port=5432, username="u@ser", password=password, dbname="d")
    parsed = make_url(build_url(server, "postgresql+psycopg2"))
    assert parsed.username == "u@ser"
    assert parsed.password == password
    assert parsed.host == "h"
    assert parsed.port == 5432
    assert parsed.database == "d"


def test_dsn_replaces_every_other_field() -> None:
    server = ServerConfig(
        hostname="ignored",
        port=1,
        username="ignored",
        password="ignored",
        dbname="ignored",
        dsn="postgresql+psycopg2://u:p@real:5432/db?sslmode=require",
    )
    url = build_url(server, "postgresql+psycopg2", database="ignored", query={"a": "b"})
    assert url == "postgresql+psycopg2://u:p@real:5432/db?sslmode=require"


def test_dsn_may_select_another_dbapi_for_the_same_dialect() -> None:
    """Swapping psycopg2 for another driver is exactly the point of a DSN."""
    server = ServerConfig(dsn="postgresql+asyncpg://u:p@h/db")
    assert build_url(server, "postgresql+psycopg2") == "postgresql+asyncpg://u:p@h/db"


def test_dsn_with_a_bare_dialect_is_accepted() -> None:
    server = ServerConfig(dsn="postgresql://u:p@h/db")
    assert build_url(server, "postgresql+psycopg2") == "postgresql://u:p@h/db"


def test_dsn_targeting_another_dialect_is_rejected() -> None:
    server = ServerConfig(dsn="mysql+pymysql://u:p@h/db")
    with pytest.raises(ConfigInvalidError, match="does not match the selected driver"):
        build_url(server, "postgresql+psycopg2")


def test_malformed_dsn_is_rejected() -> None:
    with pytest.raises(ConfigInvalidError, match="expected a '<dialect>://' URL"):
        build_url(ServerConfig(dsn="not-a-url"), "postgresql+psycopg2")


def test_fields_shadowed_by_dsn_lists_what_is_ignored() -> None:
    server = ServerConfig(hostname="h", dbname="d", dsn="postgresql://u@h/d")
    assert server.fields_shadowed_by_dsn() == ("hostname", "dbname")


def test_fields_shadowed_by_dsn_is_empty_without_a_dsn() -> None:
    assert ServerConfig(hostname="h", dbname="d").fields_shadowed_by_dsn() == ()


@pytest.mark.parametrize(
    ("url", "expected"),
    [
        ("mysql+pymysql://u:p@h:3306/main", "main"),
        ("mysql+pymysql://u:p@h/main?charset=utf8mb4", "main"),
        ("mysql+pymysql://u:p@h/my%20db", "my db"),
        ("mysql+pymysql://u:p@h/", None),
        ("mysql+pymysql://u:p@h", None),
    ],
)
def test_database_from_url(url: str, expected: object) -> None:
    assert database_from_url(url) == expected


def test_redact_url_masks_the_password() -> None:
    url = "postgresql+psycopg2://u:s3cr3t@h:5432/d"
    assert redact_url(url) == "postgresql+psycopg2://u:***@h:5432/d"


def test_redact_url_masks_an_encoded_password() -> None:
    url = "postgresql+psycopg2://u:p%40ss%2Fw@h/d"
    assert redact_url(url) == "postgresql+psycopg2://u:***@h/d"
    assert "p%40ss" not in redact_url(url)


def test_redact_url_leaves_a_credential_less_url_untouched() -> None:
    assert redact_url("sqlite:////tmp/x.db") == "sqlite:////tmp/x.db"


def test_redact_url_does_not_invent_a_password_when_there_is_none() -> None:
    """An empty password must stay empty rather than read as a masked secret."""
    assert redact_url("mysql+pymysql://u:@h/d") == "mysql+pymysql://u:@h/d"


def test_redact_url_only_touches_the_authority() -> None:
    url = "postgresql+psycopg2://u:pw@h/d?options=-c%20search_path%3Da:b@c"
    assert redact_url(url) == "postgresql+psycopg2://u:***@h/d?options=-c%20search_path%3Da:b@c"
