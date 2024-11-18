"""SQLiteSourceReader: edge cases not covered by the end-to-end test."""

from __future__ import annotations

from pathlib import Path
from typing import List
from unittest.mock import patch

import pytest

from db2sql.application.ports import Logger
from db2sql.domain.model import Column, Table
from db2sql.infrastructure.config import AppConfig, ServerConfig
from db2sql.infrastructure.persistence.errors import SourceReaderError
from db2sql.infrastructure.persistence.sqlite import SQLiteSourceReader, build_reader

from .conftest import FakeResult, FakeSession, install_fake_session


class _Logger:
    def __init__(self) -> None:
        self.errors: List[str] = []

    def trace(self, message: str) -> None: ...
    def debug(self, message: str) -> None: ...
    def info(self, message: str) -> None: ...
    def warning(self, message: str) -> None: ...
    def error(self, message: str) -> None:
        self.errors.append(message)


def _config(**server: object) -> AppConfig:
    return AppConfig(driver="sqlite", server=ServerConfig(**server))


def test_connection_string_uses_path_option() -> None:
    reader = SQLiteSourceReader(_config(options={"path": "/tmp/x.db"}), _Logger())
    assert reader._connection_string == "sqlite:////tmp/x.db"


def test_connection_string_falls_back_to_dbname() -> None:
    reader = SQLiteSourceReader(_config(dbname="foo.db"), _Logger())
    assert reader._connection_string == "sqlite:///foo.db"


def test_connection_string_without_path_raises() -> None:
    reader = SQLiteSourceReader(_config(), _Logger())
    with pytest.raises(SourceReaderError):
        _ = reader._connection_string


def test_schema_overrides_default_public() -> None:
    reader = SQLiteSourceReader(_config(dbname=":memory:", options={"schema": "custom"}), _Logger())
    install_fake_session(reader, FakeSession())
    db = reader.collect_metadata()
    assert "custom" in db.schemas


def test_collect_metadata_wraps_unexpected_exception_with_log() -> None:
    logger = _Logger()
    reader = SQLiteSourceReader(_config(dbname=":memory:"), logger)

    class _Boom:
        def execute(self, *_args, **_kwargs):
            raise RuntimeError("kaput")

    reader._ensure_session = lambda: _Boom()  # type: ignore[assignment]
    with pytest.raises(SourceReaderError):
        reader.collect_metadata()
    assert any("kaput" in msg for msg in logger.errors)


def test_collect_metadata_parses_varchar_length_and_falls_back_on_bad_length() -> None:
    reader = SQLiteSourceReader(_config(dbname=":memory:"), _Logger())
    session = FakeSession()

    def _execute_for_pragma(query, _params=None):
        query = str(query)
        if "FROM sqlite_master" in query:
            return FakeResult([("users",)])
        if "table_info" in query:
            return FakeResult(
                [
                    # cid, name, type, notnull, default, pk
                    (0, "id", "INTEGER", 1, None, 1),
                    (1, "name", "varchar(50)", 1, None, 0),
                    (2, "blob", "varchar(BAD)", 0, None, 0),
                    (3, "untyped", None, 0, None, 0),
                ]
            )
        return FakeResult([])

    session.execute = _execute_for_pragma  # type: ignore[assignment]
    install_fake_session(reader, session)

    db = reader.collect_metadata()
    users = db.schemas["public"].tables["users"]
    assert users.columns["name"].char_length == 50
    assert users.columns["name"].type == "varchar"
    assert users.columns["blob"].char_length == -1
    # untyped column falls back to TEXT
    assert users.columns["untyped"].type == "text"
    # integer pk is marked as identity (autoincrement)
    assert users.columns["id"].identity is True
    assert users.columns["id"].is_primary_key is True


def test_collect_metadata_skips_unique_pk_origin_indexes_and_records_others() -> None:
    reader = SQLiteSourceReader(_config(dbname=":memory:"), _Logger())
    session = FakeSession()

    def _execute(query, _params=None):
        query = str(query)
        if "FROM sqlite_master" in query:
            return FakeResult([("t",)])
        if "table_info" in query:
            return FakeResult(
                [
                    (0, "id", "INTEGER", 1, None, 1),
                    (1, "email", "TEXT", 0, None, 0),
                ]
            )
        if "index_list" in query:
            # seq, name, unique, origin, partial
            return FakeResult(
                [
                    (0, "sqlite_autoindex_t_1", 1, "pk", 0),
                    (1, "ux_t_email", 1, "u", 0),
                    (2, "idx_t_email", 0, "c", 0),
                ]
            )
        if "index_info" in query and "idx_t_email" in query:
            # seqno, cid, name
            return FakeResult([(0, 1, "email")])
        if "foreign_key_list" in query:
            return FakeResult([])
        return FakeResult([])

    session.execute = _execute  # type: ignore[assignment]
    install_fake_session(reader, session)

    db = reader.collect_metadata()
    table = db.schemas["public"].tables["t"]
    # only the non-unique, non-pk-origin index is recorded
    assert table.indexes == {"idx_t_email": ["email"]}


def test_collect_metadata_ignores_fk_pointing_to_unknown_column() -> None:
    reader = SQLiteSourceReader(_config(dbname=":memory:"), _Logger())
    session = FakeSession()

    def _execute(query, _params=None):
        query = str(query)
        if "FROM sqlite_master" in query:
            return FakeResult([("t",)])
        if "table_info" in query:
            return FakeResult([(0, "id", "INTEGER", 1, None, 1)])
        if "index_list" in query:
            return FakeResult([])
        if "foreign_key_list" in query:
            # id, seq, ref_table, src_col, ref_col, ...
            return FakeResult([(0, 0, "other", "missing_src", "id", "NO ACTION", "NO ACTION", "NONE")])
        return FakeResult([])

    session.execute = _execute  # type: ignore[assignment]
    install_fake_session(reader, session)

    db = reader.collect_metadata()
    # The dangling FK source column is silently ignored
    table = db.schemas["public"].tables["t"]
    assert table.columns["id"].foreign_key is None


def test_iter_rows_quotes_columns_and_table() -> None:
    reader = SQLiteSourceReader(_config(dbname=":memory:"), _Logger())
    session = FakeSession()
    session.add(lambda q, _: "SELECT" in q, [(1,), (2,)])
    install_fake_session(reader, session)

    table = Table(name="t")
    table.add_column(Column(name="id", type="int"))
    rows = list(reader.iter_rows("public", table, limit=2))
    assert rows == [(1,), (2,)]
    query, _ = session.executed[-1]
    assert '"id"' in query
    assert 'FROM "t"' in query
    assert "LIMIT 2" in query


def test_ensure_session_is_cached() -> None:
    reader = SQLiteSourceReader(_config(dbname=":memory:"), _Logger())
    with patch("db2sql.infrastructure.persistence.sqlite.reader.create_engine") as engine_factory, \
         patch(
             "db2sql.infrastructure.persistence.sqlite.reader.sessionmaker"
         ) as session_factory:
        session_factory.return_value = lambda: object()
        reader._ensure_session()
        reader._ensure_session()
    assert engine_factory.call_count == 1


def test_build_reader_returns_instance() -> None:
    assert isinstance(build_reader(_config(dbname=":memory:"), _Logger()), SQLiteSourceReader)
