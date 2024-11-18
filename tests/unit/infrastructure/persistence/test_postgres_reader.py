"""PostgresSourceReader: connection string, metadata collection, iter_rows."""

from __future__ import annotations

from unittest.mock import patch

import pytest

from db2sql.domain.model import Column, Table
from db2sql.infrastructure.config import AppConfig, ServerConfig
from db2sql.infrastructure.persistence.errors import SourceReaderError
from db2sql.infrastructure.persistence.postgres import PostgresSourceReader, build_reader

from .conftest import FakeRow, FakeSession, install_fake_session


class _StubLogger:
    def trace(self, message: str) -> None: ...
    def debug(self, message: str) -> None: ...
    def info(self, message: str) -> None: ...
    def warning(self, message: str) -> None: ...
    def error(self, message: str) -> None: ...


def _config(**server: object) -> AppConfig:
    return AppConfig(driver="postgres", server=ServerConfig(**server))


def _populated_session() -> FakeSession:
    session = FakeSession()
    session.add(
        "FROM INFORMATION_SCHEMA.TABLES",
        [
            FakeRow(TABLE_SCHEMA="public", TABLE_NAME="author"),
            FakeRow(TABLE_SCHEMA="public", TABLE_NAME="book"),
            FakeRow(TABLE_SCHEMA="other", TABLE_NAME="thing"),
        ],
    )
    session.add(
        "FROM INFORMATION_SCHEMA.COLUMNS",
        [
            FakeRow(
                TABLE_SCHEMA="public",
                TABLE_NAME="author",
                COLUMN_NAME="id",
                COLUMN_DEFAULT=None,
                IS_NULLABLE="NO",
                DATA_TYPE="integer",
                CHARACTER_MAXIMUM_LENGTH=None,
                NUMERIC_PRECISION=32,
                NUMERIC_SCALE=0,
                IS_IDENTITY="YES",
            ),
            FakeRow(
                TABLE_SCHEMA="public",
                TABLE_NAME="book",
                COLUMN_NAME="author_id",
                COLUMN_DEFAULT="0",
                IS_NULLABLE="NO",
                DATA_TYPE="integer",
                CHARACTER_MAXIMUM_LENGTH=None,
                NUMERIC_PRECISION=32,
                NUMERIC_SCALE=0,
                IS_IDENTITY="NO",
            ),
            # Column for a table the reader never collected
            FakeRow(
                TABLE_SCHEMA="ghost",
                TABLE_NAME="x",
                COLUMN_NAME="dropped",
                COLUMN_DEFAULT=None,
                IS_NULLABLE="YES",
                DATA_TYPE="text",
                CHARACTER_MAXIMUM_LENGTH=None,
                NUMERIC_PRECISION=None,
                NUMERIC_SCALE=None,
                IS_IDENTITY="NO",
            ),
        ],
    )
    session.add(
        "INFORMATION_SCHEMA.TABLE_CONSTRAINTS",
        [
            FakeRow(
                TABLE_SCHEMA="public",
                TABLE_NAME="author",
                COLUMN_NAME="id",
                CONSTRAINT_TYPE="PRIMARY KEY",
            ),
            # missing column → silently ignored
            FakeRow(
                TABLE_SCHEMA="public",
                TABLE_NAME="author",
                COLUMN_NAME="missing",
                CONSTRAINT_TYPE="UNIQUE",
            ),
        ],
    )
    session.add(
        "REFERENTIAL_CONSTRAINTS",
        [
            FakeRow(
                TABLE_SCHEMA="public",
                TABLE_NAME="book",
                COLUMN_NAME="author_id",
                REF_SCHEMA="public",
                REF_TABLE="author",
                REF_COLUMN="id",
            ),
            # column missing → ignored
            FakeRow(
                TABLE_SCHEMA="public",
                TABLE_NAME="book",
                COLUMN_NAME="zzz",
                REF_SCHEMA="public",
                REF_TABLE="author",
                REF_COLUMN="id",
            ),
            # table missing
            FakeRow(
                TABLE_SCHEMA="public",
                TABLE_NAME="phantom",
                COLUMN_NAME="x",
                REF_SCHEMA="public",
                REF_TABLE="author",
                REF_COLUMN="id",
            ),
        ],
    )
    session.add(
        "FROM pg_class",
        [
            FakeRow(
                schema_name="public",
                table_name="book",
                index_name="idx_book_author",
                column_name="author_id",
            ),
            # missing table — skipped
            FakeRow(
                schema_name="public",
                table_name="ghost",
                index_name="idx_ghost",
                column_name="x",
            ),
        ],
    )
    return session


def test_connection_string_full() -> None:
    reader = PostgresSourceReader(
        _config(hostname="h", port=5432, username="u", password="p", dbname="d"),
        _StubLogger(),
    )
    assert reader._connection_string == "postgresql+psycopg2://u:p@h:5432/d"


def test_connection_string_without_port() -> None:
    reader = PostgresSourceReader(
        _config(hostname="h", username="u", password="p", dbname="d"), _StubLogger()
    )
    assert reader._connection_string == "postgresql+psycopg2://u:p@h/d"


def test_collect_metadata_populates_all_layers() -> None:
    reader = PostgresSourceReader(_config(dbname="d"), _StubLogger())
    install_fake_session(reader, _populated_session())
    db = reader.collect_metadata()

    assert set(db.schemas) == {"public", "other"}
    public = db.schemas["public"]
    assert set(public.tables) == {"author", "book"}
    assert public.tables["author"].columns["id"].identity is True
    assert public.tables["author"].columns["id"].constraint == "PRIMARY KEY"

    fk = public.tables["book"].columns["author_id"].foreign_key
    assert fk is not None
    assert (fk.schema, fk.table, fk.column) == ("public", "author", "id")
    assert public.tables["book"].indexes == {"idx_book_author": ["author_id"]}


def test_collect_metadata_handles_empty_database_name() -> None:
    reader = PostgresSourceReader(_config(), _StubLogger())
    install_fake_session(reader, FakeSession())
    db = reader.collect_metadata()
    assert db.name == ""


def test_collect_metadata_wraps_errors() -> None:
    reader = PostgresSourceReader(_config(dbname="d"), _StubLogger())

    class _Boom:
        def execute(self, *_args, **_kwargs):
            raise RuntimeError("kaput")

    reader._ensure_session = lambda: _Boom()  # type: ignore[assignment]
    with pytest.raises(SourceReaderError):
        reader.collect_metadata()


def test_iter_rows_quotes_with_double_quotes() -> None:
    reader = PostgresSourceReader(_config(dbname="d"), _StubLogger())
    session = FakeSession()
    session.add(lambda q, _: "SELECT" in q, [(1,), (2,)])
    install_fake_session(reader, session)

    table = Table(name="t")
    table.add_column(Column(name="id", type="int"))
    list(reader.iter_rows("public", table, limit=3))
    query, _ = session.executed[-1]
    assert '"id"' in query
    assert 'FROM "public"."t"' in query
    assert "LIMIT 3" in query


def test_iter_rows_drops_limit_when_zero_or_negative() -> None:
    reader = PostgresSourceReader(_config(dbname="d"), _StubLogger())
    session = FakeSession()
    install_fake_session(reader, session)
    table = Table(name="t")
    table.add_column(Column(name="id", type="int"))
    list(reader.iter_rows("public", table, limit=0))
    list(reader.iter_rows("public", table, limit=-1))
    queries = [q for q, _ in session.executed]
    assert all("LIMIT" not in q for q in queries)


def test_ensure_session_is_cached() -> None:
    reader = PostgresSourceReader(_config(dbname="d"), _StubLogger())
    with patch("db2sql.infrastructure.persistence.postgres.reader.create_engine") as engine_factory, \
         patch(
             "db2sql.infrastructure.persistence.postgres.reader.sessionmaker"
         ) as session_factory:
        session_factory.return_value = lambda: object()
        reader._ensure_session()
        reader._ensure_session()
    assert engine_factory.call_count == 1


def test_build_reader_returns_instance() -> None:
    assert isinstance(build_reader(_config(dbname="d"), _StubLogger()), PostgresSourceReader)
