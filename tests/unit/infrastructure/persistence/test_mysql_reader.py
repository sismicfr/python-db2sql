"""MySQLSourceReader: connection string, metadata collection, iter_rows."""

from __future__ import annotations

from typing import List
from unittest.mock import patch

import pytest

from db2sql.application.ports import Logger
from db2sql.domain.model import Table
from db2sql.infrastructure.config import AppConfig, ServerConfig
from db2sql.infrastructure.persistence.errors import SourceReaderError
from db2sql.infrastructure.persistence.mysql import MySQLSourceReader, build_reader

from .conftest import FakeRow, FakeSession, install_fake_session


class _SilentLogger:
    def __init__(self) -> None:
        self.records: List[str] = []

    def trace(self, message: str) -> None: ...
    def debug(self, message: str) -> None: ...
    def info(self, message: str) -> None:
        self.records.append(("info", message))

    def warning(self, message: str) -> None:
        self.records.append(("warning", message))

    def error(self, message: str) -> None:
        self.records.append(("error", message))


def _config(**server: object) -> AppConfig:
    return AppConfig(driver="mysql", server=ServerConfig(**server))


def _full_plan() -> FakeSession:
    session = FakeSession()
    session.add(
        "FROM INFORMATION_SCHEMA.TABLES",
        [FakeRow(TABLE_NAME="author"), FakeRow(TABLE_NAME="book")],
    )
    session.add(
        "FROM INFORMATION_SCHEMA.COLUMNS",
        [
            FakeRow(
                TABLE_NAME="author",
                COLUMN_NAME="id",
                COLUMN_DEFAULT=None,
                IS_NULLABLE="NO",
                DATA_TYPE="int",
                CHARACTER_MAXIMUM_LENGTH=None,
                NUMERIC_PRECISION=10,
                NUMERIC_SCALE=0,
                EXTRA="auto_increment",
            ),
            FakeRow(
                TABLE_NAME="author",
                COLUMN_NAME="name",
                COLUMN_DEFAULT=None,
                IS_NULLABLE="NO",
                DATA_TYPE="varchar",
                CHARACTER_MAXIMUM_LENGTH=100,
                NUMERIC_PRECISION=None,
                NUMERIC_SCALE=None,
                EXTRA="",
            ),
            FakeRow(
                TABLE_NAME="book",
                COLUMN_NAME="author_id",
                COLUMN_DEFAULT=None,
                IS_NULLABLE="NO",
                DATA_TYPE="int",
                CHARACTER_MAXIMUM_LENGTH=None,
                NUMERIC_PRECISION=10,
                NUMERIC_SCALE=0,
                EXTRA="",
            ),
            FakeRow(
                TABLE_NAME="author",
                COLUMN_NAME="state",
                COLUMN_DEFAULT=None,
                IS_NULLABLE="NO",
                DATA_TYPE="char",
                CHARACTER_MAXIMUM_LENGTH=1,
                NUMERIC_PRECISION=None,
                NUMERIC_SCALE=None,
                EXTRA="",
            ),
            FakeRow(
                TABLE_NAME="book",
                COLUMN_NAME="state",
                COLUMN_DEFAULT=None,
                IS_NULLABLE="NO",
                DATA_TYPE="char",
                CHARACTER_MAXIMUM_LENGTH=1,
                NUMERIC_PRECISION=None,
                NUMERIC_SCALE=None,
                EXTRA="",
            ),
            # Belongs to a missing table — should be ignored gracefully
            FakeRow(
                TABLE_NAME="ghost",
                COLUMN_NAME="x",
                COLUMN_DEFAULT=None,
                IS_NULLABLE="YES",
                DATA_TYPE="int",
                CHARACTER_MAXIMUM_LENGTH=None,
                NUMERIC_PRECISION=10,
                NUMERIC_SCALE=0,
                EXTRA="",
            ),
        ],
    )
    session.add(
        "INFORMATION_SCHEMA.TABLE_CONSTRAINTS",
        [
            FakeRow(TABLE_NAME="author", COLUMN_NAME="id", CONSTRAINT_TYPE="PRIMARY KEY"),
            FakeRow(TABLE_NAME="ghost", COLUMN_NAME="x", CONSTRAINT_TYPE="UNIQUE"),
            FakeRow(TABLE_NAME="author", COLUMN_NAME="missing_col", CONSTRAINT_TYPE="UNIQUE"),
        ],
    )
    session.add(
        "REFERENCED_TABLE_NAME IS NOT NULL",
        [
            FakeRow(
                CONSTRAINT_NAME="fk_book_author",
                TABLE_NAME="book",
                COLUMN_NAME="author_id",
                REFERENCED_TABLE_NAME="author",
                REFERENCED_COLUMN_NAME="id",
            ),
            # Composite constraint: two rows, one per column, same name
            FakeRow(
                CONSTRAINT_NAME="fk_book_author_state",
                TABLE_NAME="book",
                COLUMN_NAME="author_id",
                REFERENCED_TABLE_NAME="author",
                REFERENCED_COLUMN_NAME="id",
            ),
            FakeRow(
                CONSTRAINT_NAME="fk_book_author_state",
                TABLE_NAME="book",
                COLUMN_NAME="state",
                REFERENCED_TABLE_NAME="author",
                REFERENCED_COLUMN_NAME="state",
            ),
            FakeRow(
                CONSTRAINT_NAME="fk_book_missing",
                TABLE_NAME="book",
                COLUMN_NAME="missing_col",
                REFERENCED_TABLE_NAME="author",
                REFERENCED_COLUMN_NAME="id",
            ),
            FakeRow(
                CONSTRAINT_NAME="fk_ghost",
                TABLE_NAME="ghost",
                COLUMN_NAME="x",
                REFERENCED_TABLE_NAME="author",
                REFERENCED_COLUMN_NAME="id",
            ),
        ],
    )
    session.add(
        "INFORMATION_SCHEMA.STATISTICS",
        [
            FakeRow(TABLE_NAME="book", INDEX_NAME="idx_book_author", COLUMN_NAME="author_id"),
            FakeRow(TABLE_NAME="ghost", INDEX_NAME="idx_x", COLUMN_NAME="x"),
        ],
    )
    return session


def test_connection_string_includes_credentials_and_port() -> None:
    reader = MySQLSourceReader(
        _config(hostname="db", port=3306, username="u", password="p", dbname="main"),
        _SilentLogger(),
    )
    assert reader._connection_string == "mysql+pymysql://u:p@db:3306/main"


def test_connection_string_omits_port_when_missing() -> None:
    reader = MySQLSourceReader(
        _config(hostname="db", username="u", password="p", dbname="main"),
        _SilentLogger(),
    )
    assert reader._connection_string == "mysql+pymysql://u:p@db/main"


def test_collect_metadata_requires_dbname() -> None:
    reader = MySQLSourceReader(_config(), _SilentLogger())
    with pytest.raises(SourceReaderError) as exc:
        reader.collect_metadata()
    assert "dbname" in str(exc.value)


def test_collect_metadata_populates_schema_tables_columns_indexes_fks() -> None:
    reader = MySQLSourceReader(_config(dbname="main"), _SilentLogger())
    install_fake_session(reader, _full_plan())

    db = reader.collect_metadata()

    schema = db.schemas["main"]
    assert set(schema.tables) == {"author", "book"}

    author = schema.tables["author"]
    assert "id" in author.columns
    assert author.columns["id"].identity is True
    assert author.columns["id"].constraint == "PRIMARY KEY"
    assert author.columns["name"].char_length == 100
    assert author.columns["name"].nullable is False

    book = schema.tables["book"]
    simple, composite = book.foreign_keys
    assert (simple.schema, simple.table) == ("main", "author")
    assert (simple.columns, simple.ref_columns) == (("author_id",), ("id",))
    assert (composite.columns, composite.ref_columns) == (
        ("author_id", "state"),
        ("id", "state"),
    )
    assert book.indexes == {"idx_book_author": ["author_id"]}


def test_collect_metadata_wraps_unexpected_exception() -> None:
    reader = MySQLSourceReader(_config(dbname="main"), _SilentLogger())

    class _BoomSession:
        def execute(self, *_args, **_kwargs):
            raise RuntimeError("boom")

    reader._ensure_session = lambda: _BoomSession()  # type: ignore[assignment]
    with pytest.raises(SourceReaderError):
        reader.collect_metadata()


def test_iter_rows_builds_backtick_quoted_query() -> None:
    reader = MySQLSourceReader(_config(dbname="main"), _SilentLogger())
    session = FakeSession()
    session.add(
        lambda q, _p: q.startswith("SELECT"),
        [(1, "a"), (2, "b")],
    )
    install_fake_session(reader, session)

    table = Table(name="author")
    from db2sql.domain.model import Column

    table.add_column(Column(name="id", type="int"))
    table.add_column(Column(name="name", type="text"))

    rows = list(reader.iter_rows("main", table, limit=5))

    assert rows == [(1, "a"), (2, "b")]
    query, _params = session.executed[-1]
    assert "`id`, `name`" in query
    assert "FROM `main`.`author`" in query
    assert "LIMIT 5" in query


def test_iter_rows_omits_limit_when_negative() -> None:
    reader = MySQLSourceReader(_config(dbname="main"), _SilentLogger())
    session = FakeSession()
    install_fake_session(reader, session)

    from db2sql.domain.model import Column

    table = Table(name="t")
    table.add_column(Column(name="id", type="int"))
    list(reader.iter_rows("main", table, limit=-1))
    query, _ = session.executed[-1]
    assert "LIMIT" not in query


def test_ensure_session_lazily_builds_engine() -> None:
    reader = MySQLSourceReader(_config(dbname="main"), _SilentLogger())
    with patch("db2sql.infrastructure.persistence.mysql.reader.create_engine") as engine_factory, \
         patch("db2sql.infrastructure.persistence.mysql.reader.sessionmaker") as session_factory:
        session_factory.return_value = lambda: object()
        first = reader._ensure_session()
        second = reader._ensure_session()
    # engine + sessionmaker called once: session is cached
    assert engine_factory.call_count == 1
    assert first is second


def test_build_reader_returns_instance() -> None:
    reader = build_reader(_config(dbname="main"), _SilentLogger())
    assert isinstance(reader, MySQLSourceReader)
