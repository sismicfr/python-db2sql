"""Unit tests for the Oracle source reader.

The reader is exercised against a :class:`FakeSession` that matches queries
by substring; no real SQLAlchemy engine or oracledb driver is required.
"""

from __future__ import annotations

import pytest

from db2sql.infrastructure.config import AppConfig, ServerConfig
from db2sql.infrastructure.logging import ConsoleLogger, LEVEL_QUIET
from db2sql.infrastructure.persistence.errors import SourceReaderError
from db2sql.infrastructure.persistence.oracle import OracleSourceReader, build_reader
from db2sql.infrastructure.persistence.oracle.reader import _normalize_oracle_type

from .conftest import FakeRow, FakeSession, install_fake_session


def _build_reader(**server_kwargs) -> OracleSourceReader:
    config = AppConfig(
        driver="oracle",
        server=ServerConfig(dbname="ORCL", **server_kwargs),
    )
    logger = ConsoleLogger(level=LEVEL_QUIET)
    return OracleSourceReader(config, logger)


def _full_plan() -> FakeSession:
    session = FakeSession()
    session.add("FROM ALL_TABLES", [FakeRow(owner="HR", table_name="EMP")])
    session.add(
        "FROM ALL_TABLES t",
        [FakeRow(owner="HR", table_name="EMP")],
    )
    session.add(
        "FROM ALL_TAB_COLUMNS",
        [
            FakeRow(
                owner="HR",
                table_name="EMP",
                column_name="ID",
                data_default=None,
                nullable="N",
                data_type="NUMBER",
                data_length=22,
                char_length=0,
                data_precision=10,
                data_scale=0,
            ),
            FakeRow(
                owner="HR",
                table_name="EMP",
                column_name="NAME",
                data_default="'unknown' ",
                nullable="Y",
                data_type="VARCHAR2",
                data_length=100,
                char_length=100,
                data_precision=None,
                data_scale=None,
            ),
            FakeRow(
                owner="HR",
                table_name="EMP",
                column_name="HIRED_AT",
                data_default=None,
                nullable="Y",
                data_type="DATE",
                data_length=7,
                char_length=0,
                data_precision=None,
                data_scale=None,
            ),
            FakeRow(
                owner="HR",
                table_name="EMP",
                column_name="DEPT_ID",
                data_default=None,
                nullable="Y",
                data_type="NUMBER",
                data_length=22,
                char_length=0,
                data_precision=10,
                data_scale=0,
            ),
        ],
    )
    session.add(
        "c.CONSTRAINT_TYPE = 'R'",
        [
            FakeRow(
                owner="HR",
                table_name="EMP",
                column_name="DEPT_ID",
                position=1,
                constraint_name="FK_EMP_DEPT",
                ref_owner="HR",
                ref_table="DEPT",
                ref_column="ID",
            )
        ],
    )
    session.add(
        "c.CONSTRAINT_TYPE IN ('P', 'U')",
        [FakeRow(owner="HR", table_name="EMP", column_name="ID", constraint_type="PRIMARY KEY")],
    )
    session.add(
        "FROM ALL_INDEXES",
        [
            FakeRow(
                table_owner="HR",
                table_name="EMP",
                index_name="IDX_EMP_NAME",
                column_name="NAME",
            )
        ],
    )
    session.add(
        "FROM ALL_TAB_IDENTITY_COLS",
        [FakeRow(owner="HR", table_name="EMP", column_name="ID")],
    )
    return session


def test_build_reader_factory_returns_oracle_reader() -> None:
    config = AppConfig(driver="oracle", server=ServerConfig(dbname="ORCL"))
    logger = ConsoleLogger(level=LEVEL_QUIET)
    assert isinstance(build_reader(config, logger), OracleSourceReader)


def test_connection_string_with_service_name() -> None:
    reader = _build_reader(
        hostname="db.local",
        port=1521,
        username="hr",
        password="pw",
        options={"service_name": "ORCLPDB1"},
    )
    assert reader._connection_string == (
        "oracle+oracledb://hr:pw@db.local:1521/?service_name=ORCLPDB1"
    )


def test_connection_string_falls_back_to_dbname() -> None:
    reader = _build_reader(hostname="db.local", port=1521, username="hr", password="pw")
    assert reader._connection_string == "oracle+oracledb://hr:pw@db.local:1521/ORCL"


def test_collect_metadata_builds_full_database() -> None:
    reader = _build_reader()
    install_fake_session(reader, _full_plan())

    database = reader.collect_metadata()

    assert list(database.schemas) == ["HR"]
    table = database.get_table("HR", "EMP")
    assert table is not None
    assert list(table.columns) == ["ID", "NAME", "HIRED_AT", "DEPT_ID"]

    id_col = table.get_column("ID")
    assert id_col is not None
    assert id_col.nullable is False
    assert id_col.constraint == "PRIMARY KEY"
    assert id_col.identity is True

    name_col = table.get_column("NAME")
    assert name_col is not None
    assert name_col.type == "varchar2"
    assert name_col.char_length == 100
    assert name_col.default == "'unknown'"

    hired_col = table.get_column("HIRED_AT")
    assert hired_col is not None
    # Oracle DATE includes time component → normalized to timestamp.
    assert hired_col.type == "timestamp"

    dept_col = table.get_column("DEPT_ID")
    assert dept_col is not None
    fk = dept_col.foreign_key
    assert fk is not None
    assert (fk.schema, fk.table, fk.column) == ("HR", "DEPT", "ID")

    assert table.indexes.get("IDX_EMP_NAME") == ["NAME"]


def test_owner_option_constrains_schema_filter() -> None:
    reader = _build_reader(options={"owner": "hr"})
    session = FakeSession()
    session.add("FROM ALL_TABLES", [FakeRow(owner="HR", table_name="EMP")])
    session.add("FROM ALL_TABLES t", [FakeRow(owner="HR", table_name="EMP")])
    session.add("FROM ALL_TAB_COLUMNS", [])
    session.add("c.CONSTRAINT_TYPE = 'R'", [])
    session.add("c.CONSTRAINT_TYPE IN ('P', 'U')", [])
    session.add("FROM ALL_INDEXES", [])
    session.add("FROM ALL_TAB_IDENTITY_COLS", [])
    install_fake_session(reader, session)

    reader.collect_metadata()

    schemas_query, schemas_params = session.executed[0]
    assert ":owner" in schemas_query
    assert schemas_params == {"owner": "HR"}


def test_collect_metadata_wraps_connection_errors() -> None:
    reader = _build_reader()

    class _BoomSession:
        def execute(self, *_args, **_kwargs):
            raise RuntimeError("ORA-12541: TNS:no listener")

    reader._ensure_session = lambda: _BoomSession()  # type: ignore[assignment]
    reader._session = _BoomSession()

    with pytest.raises(SourceReaderError):
        reader.collect_metadata()


def test_iter_rows_uses_oracle_fetch_first_for_limit() -> None:
    reader = _build_reader()
    session = FakeSession()
    session.add("FETCH FIRST", [FakeRow(id=1, name="Alice")])
    install_fake_session(reader, session)

    from db2sql.domain.model import Column, Table

    table = Table("EMP")
    table.add_column(Column(name="ID", type="number"))
    table.add_column(Column(name="NAME", type="varchar2"))

    rows = list(reader.iter_rows("HR", table, limit=10))

    assert rows == [(1, "Alice")]
    executed_query, _ = session.executed[0]
    assert "FETCH FIRST 10 ROWS ONLY" in executed_query


def test_identity_columns_query_is_optional() -> None:
    """Older Oracle versions lack ALL_TAB_IDENTITY_COLS — the reader must tolerate it."""
    reader = _build_reader()
    session = FakeSession()
    session.add("FROM ALL_TABLES", [FakeRow(owner="HR", table_name="EMP")])
    session.add("FROM ALL_TABLES t", [FakeRow(owner="HR", table_name="EMP")])
    session.add(
        "FROM ALL_TAB_COLUMNS",
        [
            FakeRow(
                owner="HR",
                table_name="EMP",
                column_name="ID",
                data_default=None,
                nullable="N",
                data_type="NUMBER",
                data_length=22,
                char_length=0,
                data_precision=10,
                data_scale=0,
            )
        ],
    )
    session.add("c.CONSTRAINT_TYPE = 'R'", [])
    session.add("c.CONSTRAINT_TYPE IN ('P', 'U')", [])
    session.add("FROM ALL_INDEXES", [])

    original_execute = session.execute

    def _execute(statement, params=None):
        if "ALL_TAB_IDENTITY_COLS" in str(statement):
            raise RuntimeError("ORA-00942: table or view does not exist")
        return original_execute(statement, params)

    session.execute = _execute  # type: ignore[assignment]
    install_fake_session(reader, session)

    database = reader.collect_metadata()
    assert database.get_table("HR", "EMP") is not None


@pytest.mark.parametrize(
    "raw, expected",
    [
        ("", ""),
        ("DATE", "timestamp"),
        ("TIMESTAMP(6)", "timestamp"),
        ("TIMESTAMP(6) WITH TIME ZONE", "timestamp with time zone"),
        ("TIMESTAMP(6) WITH LOCAL TIME ZONE", "timestamp with local time zone"),
        ("VARCHAR2(100)", "varchar2"),
        ("NUMBER", "number"),
    ],
)
def test_normalize_oracle_type(raw: str, expected: str) -> None:
    assert _normalize_oracle_type(raw) == expected


def test_ensure_session_is_cached_on_oracle() -> None:
    """Cover the lazy engine + sessionmaker creation in OracleSourceReader."""
    from unittest.mock import patch

    reader = _build_reader()
    with patch(
        "db2sql.infrastructure.persistence.oracle.reader.create_engine"
    ) as engine_factory, patch(
        "db2sql.infrastructure.persistence.oracle.reader.sessionmaker"
    ) as session_factory:
        session_factory.return_value = lambda: object()
        first = reader._ensure_session()
        second = reader._ensure_session()
    assert engine_factory.call_count == 1
    assert first is second


def test_collect_metadata_skips_rows_for_missing_columns_and_tables() -> None:
    """Cover ``if table/column is None: continue`` guards across the reader."""
    from .conftest import FakeRow as _FakeRow, FakeSession as _FakeSession

    reader = _build_reader()
    session = _FakeSession()
    session.add("DISTINCT OWNER FROM ALL_TABLES", [_FakeRow(owner="HR")])
    session.add("FROM ALL_TABLES t", [_FakeRow(owner="HR", table_name="EMP")])
    session.add(
        "FROM ALL_TAB_COLUMNS",
        [
            _FakeRow(
                owner="HR",
                table_name="EMP",
                column_name="ID",
                data_default=None,
                nullable="N",
                data_type="NUMBER",
                data_length=22,
                char_length=0,
                data_precision=10,
                data_scale=0,
            ),
            # Char column with 0 length → exercises the "if not char_length" branch
            _FakeRow(
                owner="HR",
                table_name="EMP",
                column_name="MEMO",
                data_default=None,
                nullable="Y",
                data_type="CHAR",
                data_length=10,
                char_length=0,
                data_precision=None,
                data_scale=None,
            ),
            # Column for an unknown table — must be ignored
            _FakeRow(
                owner="HR",
                table_name="GHOST",
                column_name="X",
                data_default=None,
                nullable="Y",
                data_type="NUMBER",
                data_length=22,
                char_length=0,
                data_precision=10,
                data_scale=0,
            ),
        ],
    )
    # Constraint referencing a non-existent column — must be skipped
    session.add(
        "c.CONSTRAINT_TYPE IN ('P', 'U')",
        [_FakeRow(owner="HR", table_name="EMP", column_name="MISSING", constraint_type="UNIQUE")],
    )
    # FK referencing a non-existent column AND a non-existent table
    session.add(
        "c.CONSTRAINT_TYPE = 'R'",
        [
            _FakeRow(
                owner="HR",
                table_name="EMP",
                column_name="MISSING",
                position=1,
                constraint_name="FK_EMP_MISSING",
                ref_owner="HR",
                ref_table="DEPT",
                ref_column="ID",
            ),
            _FakeRow(
                owner="HR",
                table_name="GHOST",
                column_name="X",
                position=1,
                constraint_name="FK_GHOST_DEPT",
                ref_owner="HR",
                ref_table="DEPT",
                ref_column="ID",
            ),
        ],
    )
    session.add("FROM ALL_INDEXES", [])
    # Identity row pointing to an unknown column
    session.add(
        "FROM ALL_TAB_IDENTITY_COLS",
        [_FakeRow(owner="HR", table_name="EMP", column_name="MISSING")],
    )
    install_fake_session(reader, session)
    db = reader.collect_metadata()
    emp = db.schemas["HR"].tables["EMP"]
    # Char column with CHAR_LENGTH=0 was normalized to -1
    assert emp.columns["MEMO"].char_length == -1
    # The MISSING column was never added
    assert "MISSING" not in emp.columns


def test_collect_metadata_wraps_unexpected_exception_post_schemas() -> None:
    """Exception raised *after* the schemas query goes through the generic wrap."""
    from .conftest import FakeRow as _FakeRow, FakeSession as _FakeSession

    reader = _build_reader()
    session = _FakeSession()
    session.add("DISTINCT OWNER FROM ALL_TABLES", [_FakeRow(owner="HR")])

    original_execute = session.execute

    def _execute(statement, params=None):
        text = str(statement)
        if "FROM ALL_TABLES t" in text:
            raise RuntimeError("hard failure during table read")
        return original_execute(statement, params)

    session.execute = _execute  # type: ignore[assignment]
    install_fake_session(reader, session)
    with pytest.raises(SourceReaderError) as exc:
        reader.collect_metadata()
    assert "failed to collect database information" in str(exc.value)
