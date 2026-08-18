"""Functional tests for the Oracle source reader and the postgres emitter.

Run via ``make test-functional`` after ``make stack-up``.

The fixture under .docker/oracle/init/01-schema.sql creates a TYPE_MATRIX
table in the APPTEST schema. The Oracle reader normalizes data types via
``_normalize_oracle_type``, so the types we assert against are already in
``DEFAULT_TYPE_MAP``-compatible form.
"""

from __future__ import annotations

import pytest

from db2sql.infrastructure.config import AppConfig
from db2sql.infrastructure.emit.postgres.emitter import PostgresSqlEmitter
from db2sql.infrastructure.persistence.oracle.reader import OracleSourceReader

from .conftest import require_schema

pytestmark = [pytest.mark.functional, pytest.mark.oracle]


# Mapping of column name → expected normalized type returned by
# OracleSourceReader._read_columns (post _normalize_oracle_type). Each value
# must be a key of PostgresSqlEmitter.DEFAULT_TYPE_MAP.
EXPECTED_TYPES = {
    "C_NUMBER": "number",
    "C_NUMBER_PS": "number",
    "C_BINARY_FLOAT": "binary_float",
    "C_BINARY_DOUBLE": "binary_double",
    "C_CHAR": "char",
    "C_NCHAR": "nchar",
    "C_VARCHAR2": "varchar2",
    "C_NVARCHAR2": "nvarchar2",
    "C_CLOB": "clob",
    "C_NCLOB": "nclob",
    "C_BLOB": "blob",
    "C_RAW": "raw",
    # Oracle DATE includes a time component → normalized to "timestamp"
    "C_DATE": "timestamp",
    "C_TIMESTAMP": "timestamp",
    "C_TIMESTAMP_TZ": "timestamp with time zone",
    "C_TIMESTAMP_LTZ": "timestamp with local time zone",
    "C_XML": "xmltype",
}


@pytest.fixture(scope="module")
def oracle_metadata(oracle_config: AppConfig, null_logger):
    pytest.importorskip("oracledb")
    reader = OracleSourceReader(oracle_config, null_logger)
    return require_schema(reader.collect_metadata(), "APPTEST")


def test_oracle_schema_and_tables(oracle_metadata) -> None:
    assert "APPTEST" in oracle_metadata.schemas
    schema = oracle_metadata.schemas["APPTEST"]
    assert {"TYPE_MATRIX", "TYPE_LONG", "AUTHOR", "BOOK"}.issubset(schema.tables.keys())


def test_oracle_type_matrix_columns_present(oracle_metadata) -> None:
    table = oracle_metadata.schemas["APPTEST"].get_table("TYPE_MATRIX")
    assert table is not None
    for column_name in EXPECTED_TYPES:
        assert column_name in table.columns, f"column {column_name} missing"


def test_oracle_default_type_mapping(oracle_metadata) -> None:
    table = oracle_metadata.schemas["APPTEST"].get_table("TYPE_MATRIX")
    assert table is not None
    emitter = PostgresSqlEmitter()
    for column_name, expected_source in EXPECTED_TYPES.items():
        column = table.columns[column_name]
        assert column.type.lower() == expected_source, (
            f"{column_name}: reader returned {column.type!r}, expected {expected_source!r}"
        )
        expected_target = PostgresSqlEmitter.DEFAULT_TYPE_MAP[expected_source]
        rendered = emitter.column_definition(column)
        assert expected_target.split("(")[0] in rendered, (
            f"{column_name}: rendered={rendered!r}, expected target type {expected_target!r}"
        )


def test_oracle_long_type_isolated(oracle_metadata) -> None:
    table = oracle_metadata.schemas["APPTEST"].get_table("TYPE_LONG")
    assert table is not None
    assert table.columns["PAYLOAD"].type.lower() == "long"


def test_oracle_identity_and_pk(oracle_metadata) -> None:
    table = oracle_metadata.schemas["APPTEST"].get_table("TYPE_MATRIX")
    assert table is not None
    pk_id = table.columns["ID"]
    assert pk_id.identity is True
    assert pk_id.constraint == "PRIMARY KEY"


def test_oracle_foreign_key_and_index(oracle_metadata) -> None:
    book = oracle_metadata.schemas["APPTEST"].get_table("BOOK")
    assert book is not None
    fk = book.columns["AUTHOR_ID"].foreign_key
    assert fk is not None
    assert (fk.schema, fk.table, fk.column) == ("APPTEST", "AUTHOR", "ID")
    assert any("TITLE" in cols for cols in book.indexes.values())
