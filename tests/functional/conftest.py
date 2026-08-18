"""Fixtures shared by functional tests.

These tests connect to the live MSSQL / Oracle / PostgreSQL services started
by ``docker compose --profile functional up`` (see ``.docker/docker-compose.yml``
and the ``stack-up`` make target).

Each connection fixture pre-flights the server with a short TCP probe and a
SELECT 1: if it fails or the required env vars are absent, the test is
skipped with a clear message so the suite stays green outside the stack.
"""

from __future__ import annotations

import os
import socket
from typing import Iterator

import pytest

from db2sql.domain.model import Database
from db2sql.infrastructure.config import AppConfig
from db2sql.infrastructure.config.schema import ServerConfig


class _NullLogger:
    def trace(self, message: str) -> None: ...
    def debug(self, message: str) -> None: ...
    def info(self, message: str) -> None: ...
    def warning(self, message: str) -> None: ...
    def error(self, message: str) -> None: ...


@pytest.fixture(scope="session")
def null_logger() -> _NullLogger:
    return _NullLogger()


def _require_env(*names: str) -> dict:
    missing = [n for n in names if not os.environ.get(n)]
    if missing:
        pytest.skip(f"missing env vars: {', '.join(missing)} — run `make stack-up` first")
    return {n: os.environ[n] for n in names}


def _check_tcp(host: str, port: int, timeout: float = 2.0) -> None:
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return
    except OSError as exc:
        pytest.skip(f"cannot reach {host}:{port} ({exc}) — run `make stack-up` first")


def require_schema(database: Database, schema: str) -> Database:
    """Fail early, and legibly, when the container's fixture was never loaded.

    A reachable server whose init script did not replay hands the reader an
    empty :class:`Database`. Every test in the module then dies on an opaque
    ``KeyError`` on the schema name, which says nothing about the container
    being the problem. Turn that into one sentence naming what is missing and
    what to run. This is not a skip: the server answered, so the stack is
    genuinely broken and the suite must go red.
    """
    if schema in database.schemas:
        return database
    present = ", ".join(sorted(database.schemas)) or "none"
    pytest.fail(
        f"schema {schema!r} is missing from the source database (present: {present}). "
        "The container is up but its init script has not populated it — those "
        "scripts only replay on a fresh volume, so run `make stack-reset` and "
        "start the stack again, then check `make stack-logs` for errors.",
        pytrace=False,
    )


@pytest.fixture(scope="session")
def mssql_config() -> AppConfig:
    env = _require_env(
        "MSSQL_HOST", "MSSQL_PORT", "MSSQL_USER", "MSSQL_PASSWORD", "MSSQL_DATABASE"
    )
    _check_tcp(env["MSSQL_HOST"], int(env["MSSQL_PORT"]))
    return AppConfig(
        driver="mssql",
        server=ServerConfig(
            hostname=env["MSSQL_HOST"],
            port=int(env["MSSQL_PORT"]),
            username=env["MSSQL_USER"],
            password=env["MSSQL_PASSWORD"],
            dbname=env["MSSQL_DATABASE"],
        ),
    )


@pytest.fixture(scope="session")
def oracle_config() -> AppConfig:
    env = _require_env(
        "ORACLE_HOST", "ORACLE_PORT", "ORACLE_SERVICE", "ORACLE_USER", "ORACLE_PASSWORD"
    )
    _check_tcp(env["ORACLE_HOST"], int(env["ORACLE_PORT"]))
    return AppConfig(
        driver="oracle",
        server=ServerConfig(
            hostname=env["ORACLE_HOST"],
            port=int(env["ORACLE_PORT"]),
            username=env["ORACLE_USER"],
            password=env["ORACLE_PASSWORD"],
            options={"service_name": env["ORACLE_SERVICE"], "owner": env["ORACLE_USER"]},
        ),
    )


@pytest.fixture(scope="session")
def postgres_config() -> AppConfig:
    env = _require_env(
        "PG_HOST", "PG_PORT", "PG_USER", "PG_PASSWORD", "PG_DATABASE"
    )
    _check_tcp(env["PG_HOST"], int(env["PG_PORT"]))
    return AppConfig(
        driver="postgres",
        server=ServerConfig(
            hostname=env["PG_HOST"],
            port=int(env["PG_PORT"]),
            username=env["PG_USER"],
            password=env["PG_PASSWORD"],
            dbname=env["PG_DATABASE"],
        ),
    )


@pytest.fixture(scope="session")
def mysql_config() -> AppConfig:
    env = _require_env(
        "MYSQL_HOST", "MYSQL_PORT", "MYSQL_USER", "MYSQL_PASSWORD", "MYSQL_DATABASE"
    )
    _check_tcp(env["MYSQL_HOST"], int(env["MYSQL_PORT"]))
    return AppConfig(
        driver="mysql",
        server=ServerConfig(
            hostname=env["MYSQL_HOST"],
            port=int(env["MYSQL_PORT"]),
            username=env["MYSQL_USER"],
            password=env["MYSQL_PASSWORD"],
            dbname=env["MYSQL_DATABASE"],
        ),
    )
