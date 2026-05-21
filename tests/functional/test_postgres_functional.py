"""Functional tests for the PostgreSQL source reader.

Covers two pipelines:

1. ``PostgresSourceReader`` → ``PostgresSqlEmitter`` (the canonical export
   target — types should round-trip through ``DEFAULT_TYPE_MAP`` unchanged).
2. ``PostgresSourceReader`` → ``MssqlSqlEmitter`` (the pg → mssql migration
   path: PG-native types must map to a non-empty MSSQL target type via
   ``MssqlSqlEmitter.DEFAULT_TYPE_MAP``).

Run via ``make test-functional`` after ``make stack-up`` (or ``stack-up-light``).

The fixture comes from ``.docker/postgres/init/01-schema.sql`` which creates
an ``apptest`` schema with ``type_matrix``/``author``/``book`` tables.
"""

from __future__ import annotations

import pytest

from db2sql.infrastructure.config import AppConfig
from db2sql.infrastructure.emit.mssql.emitter import MssqlSqlEmitter
from db2sql.infrastructure.emit.postgres.emitter import PostgresSqlEmitter
from db2sql.infrastructure.persistence.postgres.reader import PostgresSourceReader

pytestmark = pytest.mark.functional


# Expected source-column → pg-reported-type for every column in
# .docker/postgres/init/01-schema.sql:apptest.type_matrix. PG's
# INFORMATION_SCHEMA.COLUMNS.DATA_TYPE reports the canonical lowercase name
# (e.g. "timestamp with time zone", "double precision"); we match those 1:1
# against the keys of PostgresSqlEmitter.DEFAULT_TYPE_MAP.
EXPECTED_TYPES = {
    "c_boolean": "boolean",
    "c_smallint": "smallint",
    "c_integer": "integer",
    "c_bigint": "bigint",
    "c_real": "real",
    "c_double": "double precision",
    "c_numeric": "numeric",
    "c_decimal": "numeric",
    "c_char": "character",
    "c_varchar": "character varying",
    "c_text": "text",
    "c_bytea": "bytea",
    "c_date": "date",
    "c_time": "time without time zone",
    "c_timestamp": "timestamp without time zone",
    "c_timestamptz": "timestamp with time zone",
    "c_uuid": "uuid",
    "c_json": "json",
    "c_jsonb": "jsonb",
    "c_xml": "xml",
}


@pytest.fixture(scope="module")
def postgres_metadata(postgres_config: AppConfig, null_logger):
    pytest.importorskip("psycopg2")
    reader = PostgresSourceReader(postgres_config, null_logger)
    return reader.collect_metadata()


def test_postgres_schema_and_tables(postgres_metadata) -> None:
    assert "apptest" in postgres_metadata.schemas
    schema = postgres_metadata.schemas["apptest"]
    assert {"type_matrix", "author", "book"}.issubset(schema.tables.keys())


def test_postgres_type_matrix_columns_present(postgres_metadata) -> None:
    table = postgres_metadata.schemas["apptest"].get_table("type_matrix")
    assert table is not None
    for column_name in EXPECTED_TYPES:
        assert column_name in table.columns, f"column {column_name} missing"


def test_postgres_default_type_mapping(postgres_metadata) -> None:
    """Each PG-reported source type maps to a non-empty PG target column."""
    table = postgres_metadata.schemas["apptest"].get_table("type_matrix")
    assert table is not None
    emitter = PostgresSqlEmitter()
    for column_name, expected_source in EXPECTED_TYPES.items():
        column = table.columns[column_name]
        assert column.type.lower() == expected_source, (
            f"{column_name}: reader returned {column.type!r}, expected {expected_source!r}"
        )
        rendered = emitter.column_definition(column)
        assert rendered.strip(), f"{column_name}: emitter produced empty definition"
        # The column name must always appear; the rendered type must not be
        # empty after the name token.
        tokens = rendered.split()
        assert len(tokens) >= 2, f"{column_name}: rendered={rendered!r}"


def test_postgres_identity_and_pk(postgres_metadata) -> None:
    table = postgres_metadata.schemas["apptest"].get_table("type_matrix")
    assert table is not None
    pk_id = table.columns["id"]
    assert pk_id.identity is True
    assert pk_id.constraint == "PRIMARY KEY"


def test_postgres_foreign_key_and_index(postgres_metadata) -> None:
    book = postgres_metadata.schemas["apptest"].get_table("book")
    assert book is not None
    fk = book.columns["author_id"].foreign_key
    assert fk is not None
    assert (fk.schema, fk.table, fk.column) == ("apptest", "author", "id")
    assert any("title" in cols for cols in book.indexes.values())


# ---------------------------------------------------------------------------
# pg → mssql: same source metadata, but rendered through the MSSQL emitter.
# ---------------------------------------------------------------------------

# Subset of EXPECTED_TYPES whose PG name is a direct key of
# MssqlSqlEmitter.DEFAULT_TYPE_MAP. Multi-word PG types ("double precision",
# "timestamp with time zone") and "character"/"character varying" are not in
# the MSSQL map verbatim, so we cover those via the no-empty-render check in
# ``test_pg_to_mssql_default_type_mapping``.
PG_TO_MSSQL_EXPECTED = {
    "c_boolean": "bit",
    "c_smallint": "smallint",
    "c_bigint": "bigint",
    "c_real": "real",
    "c_numeric": "numeric",
    "c_decimal": "numeric",
    "c_text": "nvarchar(max)",
    "c_bytea": "varbinary(max)",
    "c_date": "date",
    "c_uuid": "uniqueidentifier",
    "c_json": "nvarchar(max)",
    "c_jsonb": "nvarchar(max)",
    "c_xml": "xml",
}


def test_pg_to_mssql_default_type_mapping(postgres_metadata) -> None:
    """Each PG source column renders to a non-empty MSSQL definition.

    For columns whose PG type appears verbatim in ``MssqlSqlEmitter.DEFAULT_TYPE_MAP``
    we additionally assert the expected target type is present in the output.
    """
    table = postgres_metadata.schemas["apptest"].get_table("type_matrix")
    assert table is not None
    emitter = MssqlSqlEmitter()
    for column_name in EXPECTED_TYPES:
        column = table.columns[column_name]
        rendered = emitter.column_definition(column)
        assert rendered.strip(), f"{column_name}: mssql emitter produced empty definition"
        tokens = rendered.split()
        assert len(tokens) >= 2, f"{column_name}: rendered={rendered!r}"
        expected_target = PG_TO_MSSQL_EXPECTED.get(column_name)
        if expected_target is not None:
            assert expected_target.split("(")[0] in rendered, (
                f"{column_name}: rendered={rendered!r}, "
                f"expected target type {expected_target!r}"
            )


def test_pg_to_mssql_identity_renders_as_identity(postgres_metadata) -> None:
    """PG ``GENERATED ALWAYS AS IDENTITY`` must become ``IDENTITY(1,1)`` for MSSQL."""
    table = postgres_metadata.schemas["apptest"].get_table("type_matrix")
    assert table is not None
    pk_id = table.columns["id"]
    rendered = MssqlSqlEmitter().column_definition(pk_id)
    assert "IDENTITY(1,1)" in rendered, rendered


def test_pg_to_mssql_table_emits_qualified_names(postgres_metadata) -> None:
    """Smoke-test the full table emission: schema-qualified, bracket-quoted."""
    import io

    class _Sink:
        def __init__(self) -> None:
            self.buf = io.StringIO()

        def write(self, data: str) -> None:
            self.buf.write(data)

        def boundary(self) -> None:
            pass

        def value(self) -> str:
            return self.buf.getvalue()

    sink = _Sink()
    emitter = MssqlSqlEmitter()
    emitter.emit_tables(postgres_metadata, sink)
    out = sink.value()
    assert "[apptest].[type_matrix]" in out
    assert "[apptest].[author]" in out
    assert "[apptest].[book]" in out
    # IDENTITY rendered on the PK column
    assert "IDENTITY(1,1)" in out
