"""MssqlSqlEmitter: identifier quoting, type mapping, DDL+DML rendering."""

from __future__ import annotations

import io
import warnings

import pytest

from db2sql.domain.model import Column, Database, ForeignKey, Schema, Table
from db2sql.infrastructure.emit.mssql import MssqlSqlEmitter


class _Sink:
    def __init__(self) -> None:
        self.buf = io.StringIO()
        self.boundaries = 0

    def write(self, data: str) -> None:
        self.buf.write(data)

    def boundary(self) -> None:
        self.boundaries += 1

    @property
    def text(self) -> str:
        return self.buf.getvalue()


class TestIdentifierAndTypeMapping:
    def test_preserve_case_keeps_identifier(self) -> None:
        emitter = MssqlSqlEmitter(preserve_case=True)
        assert emitter.quote_identifier("CamelCase") == "[CamelCase]"

    def test_snake_case_is_applied_when_not_preserved(self) -> None:
        emitter = MssqlSqlEmitter(preserve_case=False)
        assert emitter.quote_identifier("UserName") == "[user_name]"

    def test_embedded_closing_bracket_is_escaped(self) -> None:
        emitter = MssqlSqlEmitter(preserve_case=True)
        assert emitter.quote_identifier("weird]name") == "[weird]]name]"

    def test_schema_name_uses_mapping_when_present(self) -> None:
        emitter = MssqlSqlEmitter(preserve_case=True, schema_mapping={"dbo": "public"})
        assert emitter.schema_name(Schema(name="dbo")) == "[public]"

    @pytest.mark.parametrize(
        "source_type, char_length, precision, scale, expected",
        [
            ("integer", -1, None, None, "int"),
            ("tinyint", -1, None, None, "tinyint"),
            ("smallint", -1, None, None, "smallint"),
            ("bigint", -1, None, None, "bigint"),
            ("bit", -1, None, None, "bit"),
            ("boolean", -1, None, None, "bit"),
            ("varchar", 50, None, None, "nvarchar(50)"),
            ("varchar", -1, None, None, "nvarchar(max)"),
            ("nvarchar", 20, None, None, "nvarchar(20)"),
            ("char", 10, None, None, "nchar(10)"),
            ("text", -1, None, None, "nvarchar(max)"),
            ("clob", -1, None, None, "nvarchar(max)"),
            ("numeric", -1, 10, 2, "numeric(10,2)"),
            ("numeric", -1, 10, None, "numeric(10,0)"),
            ("uniqueidentifier", -1, None, None, "uniqueidentifier"),
            ("uuid", -1, None, None, "uniqueidentifier"),
            ("xml", -1, None, None, "xml"),
            ("json", -1, None, None, "nvarchar(max)"),
            ("jsonb", -1, None, None, "nvarchar(max)"),
            ("datetimeoffset", -1, None, None, "datetimeoffset"),
            ("timestamptz", -1, None, None, "datetimeoffset"),
            ("timestamp", -1, None, None, "datetime2"),
            ("datetime", -1, None, None, "datetime2"),
            ("blob", -1, None, None, "varbinary(max)"),
            ("bytea", -1, None, None, "varbinary(max)"),
            ("varbinary", 32, None, None, "varbinary(32)"),
            ("varbinary", -1, None, None, "varbinary(max)"),
            ("money", -1, None, None, "money"),
            ("smallmoney", -1, None, None, "smallmoney"),
            ("unknown_type", -1, None, None, "unknown_type"),
        ],
    )
    def test_type_mapping(
        self, source_type, char_length, precision, scale, expected
    ) -> None:
        emitter = MssqlSqlEmitter(preserve_case=True)
        column = Column(
            name="c",
            type=source_type,
            char_length=char_length,
            precision=precision,
            scale=scale,
        )
        assert expected in emitter.column_definition(column)


class TestColumnDefinition:
    def test_identity_int_gets_identity_suffix(self) -> None:
        emitter = MssqlSqlEmitter(preserve_case=True)
        col = Column(name="id", type="int", identity=True)
        assert emitter.column_definition(col) == "[id] int IDENTITY(1,1)"

    def test_identity_bigint_gets_identity_suffix(self) -> None:
        emitter = MssqlSqlEmitter(preserve_case=True)
        col = Column(name="id", type="bigint", identity=True)
        assert emitter.column_definition(col) == "[id] bigint IDENTITY(1,1)"

    def test_not_null_default(self) -> None:
        emitter = MssqlSqlEmitter(preserve_case=True)
        col = Column(name="email", type="varchar", char_length=255, nullable=False, default="''")
        assert emitter.column_definition(col) == "[email] nvarchar(255) NOT NULL DEFAULT ''"


class TestTransactionAndSchemas:
    def test_prologue_uses_begin_transaction(self) -> None:
        emitter = MssqlSqlEmitter(preserve_case=True)
        sink = _Sink()
        emitter.emit_prologue(sink)
        assert sink.text == "BEGIN TRANSACTION;\n\n"

    def test_epilogue_uses_commit_transaction(self) -> None:
        emitter = MssqlSqlEmitter(preserve_case=True)
        sink = _Sink()
        emitter.emit_epilogue(sink)
        assert sink.text == "COMMIT TRANSACTION;\n"

    def test_emit_schemas_uses_if_not_exists_exec(self) -> None:
        emitter = MssqlSqlEmitter(preserve_case=True)
        db = Database(name="main")
        db.add_schema(Schema(name="dbo"))
        db.add_schema(Schema(name="audit"))
        sink = _Sink()
        emitter.emit_schemas(db, sink)
        text = sink.text
        assert text.count("IF NOT EXISTS (SELECT 1 FROM sys.schemas WHERE name = N'") == 2
        assert "EXEC('CREATE SCHEMA [dbo]')" in text
        assert "EXEC('CREATE SCHEMA [audit]')" in text

    def test_emit_schemas_dedups_via_mapping(self) -> None:
        emitter = MssqlSqlEmitter(
            preserve_case=True, schema_mapping={"dbo": "common", "audit": "common"}
        )
        db = Database(name="main")
        db.add_schema(Schema(name="dbo"))
        db.add_schema(Schema(name="audit"))
        sink = _Sink()
        emitter.emit_schemas(db, sink)
        assert sink.text.count("EXEC('CREATE SCHEMA [common]')") == 1

    def test_emit_schemas_escapes_quote_in_literal(self) -> None:
        emitter = MssqlSqlEmitter(preserve_case=True)
        db = Database(name="main")
        db.add_schema(Schema(name="o'reilly"))
        sink = _Sink()
        emitter.emit_schemas(db, sink)
        assert "WHERE name = N'o''reilly'" in sink.text


class TestEmitTablesFkIndexes:
    def _db(self) -> Database:
        db = Database(name="main")
        public = Schema(name="public")
        author = Table(name="author")
        author.add_column(Column(name="id", type="int", identity=True, constraint="PRIMARY KEY"))
        author.add_column(Column(name="name", type="varchar", char_length=120, nullable=False))
        public.add_table(author)
        db.add_schema(public)
        return db

    def test_emit_tables_emits_primary_key(self) -> None:
        emitter = MssqlSqlEmitter(preserve_case=True)
        sink = _Sink()
        emitter.emit_tables(self._db(), sink)
        text = sink.text
        assert "CREATE TABLE [public].[author]" in text
        assert "[id] int IDENTITY(1,1)" in text
        assert "[name] nvarchar(120) NOT NULL" in text
        assert "PRIMARY KEY ([id])" in text

    def test_emit_foreign_keys_with_valid_reference(self) -> None:
        emitter = MssqlSqlEmitter(preserve_case=True)
        db = self._db()
        book = Table(name="book")
        col = Column(name="author_id", type="int")
        col.foreign_key = ForeignKey("public", "author", "id")
        book.add_column(col)
        db.schemas["public"].add_table(book)
        sink = _Sink()
        emitter.emit_foreign_keys(db, sink)
        text = sink.text
        assert "ALTER TABLE [public].[book]" in text
        assert "REFERENCES [public].[author] ([id])" in text

    def test_emit_foreign_keys_skips_dangling_refs(self) -> None:
        emitter = MssqlSqlEmitter(preserve_case=True)
        db = self._db()
        book = Table(name="book")
        col = Column(name="author_id", type="int")
        col.foreign_key = ForeignKey("missing", "author", "id")
        book.add_column(col)
        db.schemas["public"].add_table(book)
        sink = _Sink()
        emitter.emit_foreign_keys(db, sink)
        assert "ALTER TABLE" not in sink.text

    def test_emit_indexes(self) -> None:
        emitter = MssqlSqlEmitter(preserve_case=True)
        db = self._db()
        db.schemas["public"].tables["author"].add_index("idx_name", "name")
        sink = _Sink()
        emitter.emit_indexes(db, sink)
        assert "CREATE INDEX [idx_name] ON [public].[author] ([name])" in sink.text

    def test_emit_drops_uses_sql_server_2016_syntax_in_reverse_order(self) -> None:
        emitter = MssqlSqlEmitter(preserve_case=True)
        db = self._db()
        book = Table(name="book")
        book.add_column(Column(name="author_id", type="int",
                               foreign_key=ForeignKey("public", "author", "id")))
        db.schemas["public"].add_table(book)
        sink = _Sink()
        emitter.emit_drops(db, sink)
        text = sink.text
        assert "DROP TABLE IF EXISTS [public].[book];" in text
        assert "DROP TABLE IF EXISTS [public].[author];" in text
        assert text.index("[public].[book]") < text.index("[public].[author]")

    def test_emit_truncates_emits_per_table_in_reverse_order(self) -> None:
        emitter = MssqlSqlEmitter(preserve_case=True)
        db = self._db()
        book = Table(name="book")
        book.add_column(Column(name="author_id", type="int",
                               foreign_key=ForeignKey("public", "author", "id")))
        db.schemas["public"].add_table(book)
        sink = _Sink()
        emitter.emit_truncates(db, sink)
        text = sink.text
        assert "TRUNCATE TABLE [public].[book];" in text
        assert "TRUNCATE TABLE [public].[author];" in text
        assert text.index("[public].[book]") < text.index("[public].[author]")

    def test_emit_truncates_emits_dbcc_checkident_only_for_identity_tables(self) -> None:
        emitter = MssqlSqlEmitter(preserve_case=True)
        db = self._db()  # author has identity id
        # book has no identity column
        book = Table(name="book")
        book.add_column(Column(name="id", type="int", constraint="PRIMARY KEY"))
        db.schemas["public"].add_table(book)
        sink = _Sink()
        emitter.emit_truncates(db, sink)
        text = sink.text
        assert "DBCC CHECKIDENT ('[public].[author]', RESEED, 0);" in text
        assert "[public].[book]'" not in text  # no DBCC line for book

    def test_emit_truncates_on_empty_database_writes_nothing(self) -> None:
        emitter = MssqlSqlEmitter(preserve_case=True)
        sink = _Sink()
        emitter.emit_truncates(Database(name="main"), sink)
        assert "TRUNCATE" not in sink.text
        assert "DBCC" not in sink.text


class TestRowFormatting:
    def _table(self) -> tuple[Schema, Table]:
        schema = Schema(name="public")
        table = Table(name="t")
        table.add_column(Column(name="id", type="int"))
        table.add_column(Column(name="name", type="varchar", char_length=100))
        return schema, table

    def test_insert_handles_null_bool_bytes_and_quote_escape(self) -> None:
        emitter = MssqlSqlEmitter(preserve_case=True)
        schema, table = self._table()
        rows = [
            (None, "Bob"),
            (1, "O'Reilly"),
            (2, b"\x00\xff"),
            (3, True),
            (4, False),
        ]
        sink = _Sink()
        emitter.emit_data_insert(schema, table, rows, sink)
        text = sink.text
        assert "VALUES (NULL, N'Bob');" in text
        assert "VALUES (1, N'O''Reilly');" in text
        assert "VALUES (2, 0x00ff);" in text
        assert "VALUES (3, 1);" in text  # bool True → 1
        assert "VALUES (4, 0);" in text  # bool False → 0

    def test_copy_falls_back_to_insert_with_warning(self) -> None:
        emitter = MssqlSqlEmitter(preserve_case=True)
        schema, table = self._table()
        rows = [(1, "ok")]
        sink = _Sink()
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            emitter.emit_data_copy(schema, table, rows, sink)
        assert any("COPY is Postgres-only" in str(w.message) for w in caught)
        # The output should be INSERT statements, not a COPY block.
        assert "COPY" not in sink.text
        assert "INSERT INTO [public].[t]" in sink.text

    def test_copy_warning_is_emitted_only_once(self) -> None:
        emitter = MssqlSqlEmitter(preserve_case=True)
        schema, table = self._table()
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            emitter.emit_data_copy(schema, table, [(1, "a")], _Sink())
            emitter.emit_data_copy(schema, table, [(2, "b")], _Sink())
        assert sum(1 for w in caught if "COPY is Postgres-only" in str(w.message)) == 1
