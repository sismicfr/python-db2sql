"""Functional tests for the MySQL source reader and the postgres emitter.

Run via ``make test-functional`` after ``make stack-up`` (or ``stack-up-light``).

The fixture comes from ``.docker/mysql/init/01-schema.sql``: a ``db2sqltest``
database with a ``type_matrix`` table (covering MySQL-native source types
referenced by ``PostgresSqlEmitter.DEFAULT_TYPE_MAP``) plus the standard
author/book relational fixture.

MySQL has no notion of "schema" separate from "database", so the reader
exposes the database name as a single schema entry.
"""

from __future__ import annotations

import pytest

from db2sql.infrastructure.config import AppConfig
from db2sql.infrastructure.emit.postgres.emitter import PostgresSqlEmitter
from db2sql.infrastructure.persistence.mysql.reader import MySQLSourceReader

pytestmark = pytest.mark.functional


# Expected source-column → mysql-reported-type for every column in
# .docker/mysql/init/01-schema.sql:type_matrix.
# MySQL's INFORMATION_SCHEMA.COLUMNS.DATA_TYPE returns the canonical
# lowercase name without precision (e.g. "varchar" not "varchar(64)"), so
# we match those 1:1 against the keys of PostgresSqlEmitter.DEFAULT_TYPE_MAP.
EXPECTED_TYPES = {
    "c_bit": "bit",
    "c_tinyint": "tinyint",
    "c_smallint": "smallint",
    "c_mediumint": "mediumint",
    "c_int": "int",
    "c_bigint": "bigint",
    "c_decimal": "decimal",
    "c_numeric": "decimal",  # MySQL aliases NUMERIC → DECIMAL
    "c_float": "float",
    "c_double": "double",
    "c_char": "char",
    "c_varchar": "varchar",
    "c_text": "text",
    "c_mediumtext": "mediumtext",
    "c_longtext": "longtext",
    "c_binary": "binary",
    "c_varbinary": "varbinary",
    "c_blob": "blob",
    "c_date": "date",
    "c_time": "time",
    "c_datetime": "datetime",
    "c_timestamp": "timestamp",
    "c_json": "json",
}


@pytest.fixture(scope="module")
def mysql_metadata(mysql_config: AppConfig, null_logger):
    pytest.importorskip("pymysql")
    reader = MySQLSourceReader(mysql_config, null_logger)
    return reader.collect_metadata()


def test_mysql_schema_and_tables(mysql_metadata) -> None:
    # The reader uses the database name as the schema key.
    assert "db2sqltest" in mysql_metadata.schemas
    schema = mysql_metadata.schemas["db2sqltest"]
    assert {"type_matrix", "author", "book"}.issubset(schema.tables.keys())


def test_mysql_type_matrix_columns_present(mysql_metadata) -> None:
    table = mysql_metadata.schemas["db2sqltest"].get_table("type_matrix")
    assert table is not None
    for column_name in EXPECTED_TYPES:
        assert column_name in table.columns, f"column {column_name} missing"


def test_mysql_default_type_mapping(mysql_metadata) -> None:
    table = mysql_metadata.schemas["db2sqltest"].get_table("type_matrix")
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


def test_mysql_identity_and_pk(mysql_metadata) -> None:
    table = mysql_metadata.schemas["db2sqltest"].get_table("type_matrix")
    assert table is not None
    pk_id = table.columns["id"]
    assert pk_id.identity is True, "AUTO_INCREMENT should mark the column as identity"
    assert pk_id.constraint == "PRIMARY KEY"


def test_mysql_foreign_key_and_index(mysql_metadata) -> None:
    book = mysql_metadata.schemas["db2sqltest"].get_table("book")
    assert book is not None
    fk = book.columns["author_id"].foreign_key
    assert fk is not None
    assert (fk.schema, fk.table, fk.column) == ("db2sqltest", "author", "id")
    assert any("title" in cols for cols in book.indexes.values())
