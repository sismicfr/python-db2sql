"""MSSQLSourceReader: connection string, metadata collection, iter_rows."""

from __future__ import annotations

from unittest.mock import patch

import pytest

from db2sql.domain.model import Column, Table
from db2sql.infrastructure.config import AppConfig, ServerConfig
from db2sql.infrastructure.persistence.errors import SourceReaderError
from db2sql.infrastructure.persistence.mssql import MSSQLSourceReader, build_reader

from .conftest import FakeRow, FakeSession, install_fake_session


class _StubLogger:
    def trace(self, message: str) -> None: ...
    def debug(self, message: str) -> None: ...
    def info(self, message: str) -> None: ...
    def warning(self, message: str) -> None: ...
    def error(self, message: str) -> None: ...


def _config(**server: object) -> AppConfig:
    return AppConfig(driver="mssql", server=ServerConfig(**server))


def _populated_session() -> FakeSession:
    session = FakeSession()
    session.add(
        "INFORMATION_SCHEMA.SCHEMATA",
        [FakeRow(SCHEMA_NAME="dbo"), FakeRow(SCHEMA_NAME="audit")],
    )
    session.add(
        "TABLE_TYPE = 'BASE TABLE'",
        [
            FakeRow(TABLE_SCHEMA="dbo", TABLE_NAME="Customer"),
            FakeRow(TABLE_SCHEMA="dbo", TABLE_NAME="Order"),
        ],
    )
    session.add(
        "INFORMATION_SCHEMA.COLUMNS",
        [
            FakeRow(
                TABLE_SCHEMA="dbo",
                TABLE_NAME="Customer",
                COLUMN_NAME="Id",
                COLUMN_DEFAULT=None,
                IS_NULLABLE="NO",
                DATA_TYPE="int",
                CHARACTER_MAXIMUM_LENGTH=None,
                NUMERIC_PRECISION=10,
                NUMERIC_SCALE=0,
            ),
            FakeRow(
                TABLE_SCHEMA="dbo",
                TABLE_NAME="Order",
                COLUMN_NAME="CustomerId",
                COLUMN_DEFAULT=None,
                IS_NULLABLE="NO",
                DATA_TYPE="int",
                CHARACTER_MAXIMUM_LENGTH=None,
                NUMERIC_PRECISION=10,
                NUMERIC_SCALE=0,
            ),
            FakeRow(
                TABLE_SCHEMA="dbo",
                TABLE_NAME="Customer",
                COLUMN_NAME="State",
                COLUMN_DEFAULT=None,
                IS_NULLABLE="NO",
                DATA_TYPE="char",
                CHARACTER_MAXIMUM_LENGTH=1,
                NUMERIC_PRECISION=None,
                NUMERIC_SCALE=None,
            ),
            FakeRow(
                TABLE_SCHEMA="dbo",
                TABLE_NAME="Order",
                COLUMN_NAME="State",
                COLUMN_DEFAULT=None,
                IS_NULLABLE="NO",
                DATA_TYPE="char",
                CHARACTER_MAXIMUM_LENGTH=1,
                NUMERIC_PRECISION=None,
                NUMERIC_SCALE=None,
            ),
            # Belongs to a table we never collected — must be ignored
            FakeRow(
                TABLE_SCHEMA="dbo",
                TABLE_NAME="Phantom",
                COLUMN_NAME="X",
                COLUMN_DEFAULT=None,
                IS_NULLABLE="YES",
                DATA_TYPE="int",
                CHARACTER_MAXIMUM_LENGTH=None,
                NUMERIC_PRECISION=10,
                NUMERIC_SCALE=0,
            ),
        ],
    )
    session.add(
        "SYS.COMPUTED_COLUMNS",
        [
            FakeRow(
                TABLE_SCHEMA="dbo",
                TABLE_NAME="Customer",
                COLUMN_NAME="Id",
                DEFINITION="([Id]+1)",
            ),
            FakeRow(
                TABLE_SCHEMA="dbo",
                TABLE_NAME="Customer",
                COLUMN_NAME="Missing",
                DEFINITION="x",
            ),
            FakeRow(
                TABLE_SCHEMA="dbo",
                TABLE_NAME="Phantom",
                COLUMN_NAME="X",
                DEFINITION="x",
            ),
        ],
    )
    session.add(
        "sys.identity_columns",
        [
            FakeRow(TABLE_SCHEMA="dbo", TABLE_NAME="Customer", COLUMN_NAME="Id"),
            FakeRow(TABLE_SCHEMA="dbo", TABLE_NAME="Customer", COLUMN_NAME="Missing"),
            FakeRow(TABLE_SCHEMA="dbo", TABLE_NAME="Phantom", COLUMN_NAME="X"),
        ],
    )
    session.add(
        "CONSTRAINT_COLUMN_USAGE",
        [
            FakeRow(
                TABLE_SCHEMA="dbo",
                TABLE_NAME="Customer",
                COLUMN_NAME="Id",
                CONSTRAINT_TYPE="PRIMARY KEY",
            ),
            # missing column → skipped
            FakeRow(
                TABLE_SCHEMA="dbo",
                TABLE_NAME="Customer",
                COLUMN_NAME="Missing",
                CONSTRAINT_TYPE="UNIQUE",
            ),
            FakeRow(
                TABLE_SCHEMA="dbo",
                TABLE_NAME="Phantom",
                COLUMN_NAME="X",
                CONSTRAINT_TYPE="UNIQUE",
            ),
        ],
    )
    session.add(
        "REFERENTIAL_CONSTRAINTS",
        [
            FakeRow(
                TABLE_SCHEMA="dbo",
                TABLE_NAME="Order",
                CONSTRAINT_NAME="FK_Order_Customer",
                COLUMN_NAME="CustomerId",
                UNIQUE_TABLE_SCHEMA="dbo",
                UNIQUE_TABLE_NAME="Customer",
                UNIQUE_COLUMN_NAME="Id",
            ),
            # Composite constraint: two rows, one per column, same name
            FakeRow(
                TABLE_SCHEMA="dbo",
                TABLE_NAME="Order",
                CONSTRAINT_NAME="FK_Order_Customer_State",
                COLUMN_NAME="CustomerId",
                UNIQUE_TABLE_SCHEMA="dbo",
                UNIQUE_TABLE_NAME="Customer",
                UNIQUE_COLUMN_NAME="Id",
            ),
            FakeRow(
                TABLE_SCHEMA="dbo",
                TABLE_NAME="Order",
                CONSTRAINT_NAME="FK_Order_Customer_State",
                COLUMN_NAME="State",
                UNIQUE_TABLE_SCHEMA="dbo",
                UNIQUE_TABLE_NAME="Customer",
                UNIQUE_COLUMN_NAME="State",
            ),
            FakeRow(
                TABLE_SCHEMA="dbo",
                TABLE_NAME="Order",
                CONSTRAINT_NAME="FK_Order_Missing",
                COLUMN_NAME="Missing",
                UNIQUE_TABLE_SCHEMA="dbo",
                UNIQUE_TABLE_NAME="Customer",
                UNIQUE_COLUMN_NAME="Id",
            ),
            FakeRow(
                TABLE_SCHEMA="dbo",
                TABLE_NAME="Phantom",
                CONSTRAINT_NAME="FK_Phantom",
                COLUMN_NAME="X",
                UNIQUE_TABLE_SCHEMA="dbo",
                UNIQUE_TABLE_NAME="Customer",
                UNIQUE_COLUMN_NAME="Id",
            ),
        ],
    )
    session.add(
        "sys.indexes",
        [
            FakeRow(
                TABLE_SCHEMA="dbo",
                TABLE_NAME="Order",
                INDEX_NAME="idx_order_cust",
                INDEX_ID=2,
                COLUMN_ID=1,
                COLUMN_NAME="CustomerId",
            ),
            FakeRow(
                TABLE_SCHEMA="dbo",
                TABLE_NAME="Phantom",
                INDEX_NAME="idx_phantom",
                INDEX_ID=2,
                COLUMN_ID=1,
                COLUMN_NAME="X",
            ),
        ],
    )
    return session


def test_connection_string_full() -> None:
    reader = MSSQLSourceReader(
        _config(hostname="h", port=1433, username="u", password="p", dbname="d"),
        _StubLogger(),
    )
    assert reader._connection_string == "mssql+pymssql://u:p@h:1433/d"


def test_connection_string_without_port() -> None:
    reader = MSSQLSourceReader(
        _config(hostname="h", username="u", password="p", dbname="d"), _StubLogger()
    )
    assert reader._connection_string == "mssql+pymssql://u:p@h/d"


def test_collect_metadata_collects_everything() -> None:
    reader = MSSQLSourceReader(_config(dbname="d"), _StubLogger())
    install_fake_session(reader, _populated_session())
    db = reader.collect_metadata()

    assert set(db.schemas) == {"dbo", "audit"}
    customer = db.schemas["dbo"].tables["Customer"]
    assert customer.columns["Id"].identity is True
    assert customer.columns["Id"].constraint == "PRIMARY KEY"
    assert customer.columns["Id"].computed_definition == "([Id]+1)"
    order = db.schemas["dbo"].tables["Order"]
    simple, composite = order.foreign_keys
    assert (simple.schema, simple.table) == ("dbo", "Customer")
    assert (simple.columns, simple.ref_columns) == (("CustomerId",), ("Id",))
    assert (composite.columns, composite.ref_columns) == (
        ("CustomerId", "State"),
        ("Id", "State"),
    )
    assert order.indexes == {"idx_order_cust": ["CustomerId"]}


def test_read_schemas_wraps_connection_error() -> None:
    """The very first query (schemas) is special-cased to raise a clearer error."""
    reader = MSSQLSourceReader(_config(dbname="d"), _StubLogger())

    class _BoomSession:
        def execute(self, *_args, **_kwargs):
            raise RuntimeError("no driver")

    reader._ensure_session = lambda: _BoomSession()  # type: ignore[assignment]
    with pytest.raises(SourceReaderError) as exc:
        reader.collect_metadata()
    # _read_schemas raises SourceReaderError("Error connecting...") from the underlying
    # exception, the outer try/except wraps it into a generic message but the chain
    # still points to the original cause.
    assert isinstance(exc.value.__cause__, SourceReaderError)
    assert "Error connecting to database" in str(exc.value.__cause__)


def test_iter_rows_quotes_with_brackets() -> None:
    reader = MSSQLSourceReader(_config(dbname="d"), _StubLogger())
    session = FakeSession()
    session.add(lambda q, _: "SELECT" in q, [(1, "x")])
    install_fake_session(reader, session)

    table = Table(name="Customer")
    table.add_column(Column(name="Id", type="int"))
    table.add_column(Column(name="Name", type="varchar"))
    rows = list(reader.iter_rows("dbo", table, limit=7))
    assert rows == [(1, "x")]
    query, _ = session.executed[-1]
    assert "TOP 7" in query
    assert "[Id], [Name]" in query
    assert "FROM [dbo].[Customer]" in query


def test_iter_rows_no_top_when_unlimited() -> None:
    reader = MSSQLSourceReader(_config(dbname="d"), _StubLogger())
    session = FakeSession()
    install_fake_session(reader, session)
    table = Table(name="t")
    table.add_column(Column(name="id", type="int"))
    list(reader.iter_rows("dbo", table, limit=-1))
    query, _ = session.executed[-1]
    assert "TOP" not in query


def test_ensure_session_is_cached() -> None:
    reader = MSSQLSourceReader(_config(dbname="d"), _StubLogger())
    with patch("db2sql.infrastructure.persistence.mssql.reader.create_engine") as engine_factory, \
         patch("db2sql.infrastructure.persistence.mssql.reader.sessionmaker") as session_factory:
        session_factory.return_value = lambda: object()
        reader._ensure_session()
        reader._ensure_session()
    assert engine_factory.call_count == 1


def test_build_reader_returns_instance() -> None:
    assert isinstance(build_reader(_config(dbname="d"), _StubLogger()), MSSQLSourceReader)
