"""Functional tests for the MSSQL source reader and the postgres emitter.

Run via ``make test-functional`` after ``make stack-up`` (or rely on the
``stack-up`` prerequisite of ``test-functional``).

What we validate:
1. ``MSSQLSourceReader.collect_metadata`` returns the apptest schema with the
   expected tables.
2. Every column of ``type_matrix`` is collected and produces a non-empty
   PostgreSQL type when fed through ``PostgresSqlEmitter.column_definition``.
3. Each source type covered by the fixture is mapped to the expected
   target type from ``PostgresSqlEmitter.DEFAULT_TYPE_MAP``.
4. The author/book relationship (PK identity + FK + secondary index) is
   surfaced correctly.
"""

from __future__ import annotations

import pytest

from db2sql.infrastructure.config import AppConfig
from db2sql.infrastructure.emit.postgres.emitter import PostgresSqlEmitter
from db2sql.infrastructure.persistence.mssql.reader import MSSQLSourceReader

pytestmark = pytest.mark.functional


# Expected source-column → mssql-reported-type for every column in
# .docker/mssql/init/01-schema.sql:type_matrix. MSSQL's INFORMATION_SCHEMA
# reports a lowercase type name without precision; we match it 1:1 against
# the keys of PostgresSqlEmitter.DEFAULT_TYPE_MAP.
EXPECTED_TYPES = {
    "c_bit": "bit",
    "c_tinyint": "tinyint",
    "c_smallint": "smallint",
    "c_int": "int",
    "c_bigint": "bigint",
    "c_real": "real",
    "c_float": "float",
    "c_decimal": "decimal",
    "c_numeric": "numeric",
    "c_money": "money",
    "c_smallmoney": "smallmoney",
    "c_char": "char",
    "c_nchar": "nchar",
    "c_varchar": "varchar",
    "c_nvarchar": "nvarchar",
    "c_text": "text",
    "c_ntext": "ntext",
    "c_binary": "binary",
    "c_varbinary": "varbinary",
    "c_image": "image",
    "c_date": "date",
    "c_time": "time",
    "c_datetime": "datetime",
    "c_datetime2": "datetime2",
    "c_smalldatetime": "smalldatetime",
    "c_datetimeoffset": "datetimeoffset",
    "c_uniqueidentifier": "uniqueidentifier",
    "c_xml": "xml",
}


@pytest.fixture(scope="module")
def mssql_metadata(mssql_config: AppConfig, null_logger):
    pytest.importorskip("pymssql")
    reader = MSSQLSourceReader(mssql_config, null_logger)
    return reader.collect_metadata()


def test_mssql_schema_and_tables(mssql_metadata) -> None:
    assert "apptest" in mssql_metadata.schemas
    schema = mssql_metadata.schemas["apptest"]
    assert {"type_matrix", "author", "book"}.issubset(schema.tables.keys())


def test_mssql_type_matrix_columns_present(mssql_metadata) -> None:
    table = mssql_metadata.schemas["apptest"].get_table("type_matrix")
    assert table is not None
    for column_name in EXPECTED_TYPES:
        assert column_name in table.columns, f"column {column_name} missing"


def test_mssql_default_type_mapping(mssql_metadata) -> None:
    table = mssql_metadata.schemas["apptest"].get_table("type_matrix")
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


def test_mssql_identity_and_pk(mssql_metadata) -> None:
    table = mssql_metadata.schemas["apptest"].get_table("type_matrix")
    assert table is not None
    pk_id = table.columns["id"]
    assert pk_id.identity is True
    assert pk_id.constraint == "PRIMARY KEY"


def test_mssql_computed_column_detected(mssql_metadata) -> None:
    table = mssql_metadata.schemas["apptest"].get_table("type_matrix")
    assert table is not None
    computed = table.columns.get("computed_full")
    assert computed is not None
    assert computed.computed_definition, "computed_full should expose a definition"


def test_mssql_foreign_key_and_index(mssql_metadata) -> None:
    book = mssql_metadata.schemas["apptest"].get_table("book")
    assert book is not None
    assert book.columns["author_id"].foreign_key is not None
    fk = book.columns["author_id"].foreign_key
    assert (fk.schema, fk.table, fk.column) == ("apptest", "author", "id")
    assert any("title" in cols for cols in book.indexes.values())
