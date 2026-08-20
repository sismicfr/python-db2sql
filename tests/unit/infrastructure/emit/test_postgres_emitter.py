"""PostgresSqlEmitter: identifier quoting, type mapping, DDL+DML rendering."""

from __future__ import annotations

import io

import pytest

from db2sql.domain.model import Column, Database, ForeignKey, Schema, Table
from db2sql.infrastructure.emit.postgres import PostgresSqlEmitter


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
        emitter = PostgresSqlEmitter(preserve_case=True)
        assert emitter.quote_identifier("CamelCase") == '"CamelCase"'

    def test_snake_case_is_applied_when_not_preserved(self) -> None:
        emitter = PostgresSqlEmitter(preserve_case=False)
        assert emitter.quote_identifier("UserName") == '"user_name"'

    def test_embedded_quotes_are_escaped(self) -> None:
        emitter = PostgresSqlEmitter(preserve_case=True)
        assert emitter.quote_identifier('weird"name') == '"weird""name"'

    def test_schema_name_uses_mapping_when_present(self) -> None:
        emitter = PostgresSqlEmitter(preserve_case=True, schema_mapping={"dbo": "public"})
        assert emitter.schema_name(Schema(name="dbo")) == '"public"'

    def test_schema_name_falls_back_to_original_when_unmapped(self) -> None:
        emitter = PostgresSqlEmitter(preserve_case=True)
        assert emitter.schema_name(Schema(name="public")) == '"public"'

    @pytest.mark.parametrize(
        "source_type, char_length, precision, scale, expected",
        [
            ("integer", -1, None, None, "integer"),
            ("tinyint", -1, None, None, "smallint"),
            ("varchar", 50, None, None, "varchar(50)"),
            ("varchar", -1, None, None, "varchar"),
            ("nvarchar", 20, None, None, "varchar(20)"),
            ("numeric", -1, 10, 2, "numeric(10,2)"),
            ("numeric", -1, 10, None, "numeric(10,0)"),
            ("uniqueidentifier", -1, None, None, "uuid"),
            ("xml", -1, None, None, "xml"),
            ("json", -1, None, None, "jsonb"),
            ("datetimeoffset", -1, None, None, "timestamptz"),
            ("blob", -1, None, None, "bytea"),
            ("unknown_type", -1, None, None, "unknown_type"),
        ],
    )
    def test_type_mapping(
        self, source_type, char_length, precision, scale, expected
    ) -> None:
        emitter = PostgresSqlEmitter(preserve_case=True)
        column = Column(
            name="c",
            type=source_type,
            char_length=char_length,
            precision=precision,
            scale=scale,
        )
        assert expected in emitter.column_definition(column)


class TestColumnDefinition:
    def test_identity_integer_becomes_serial(self) -> None:
        emitter = PostgresSqlEmitter(preserve_case=True)
        col = Column(name="id", type="int", identity=True)
        assert emitter.column_definition(col) == '"id" serial'

    def test_identity_bigint_becomes_bigserial(self) -> None:
        emitter = PostgresSqlEmitter(preserve_case=True)
        col = Column(name="id", type="bigint", identity=True)
        assert emitter.column_definition(col) == '"id" bigserial'

    def test_not_null_default(self) -> None:
        emitter = PostgresSqlEmitter(preserve_case=True)
        col = Column(name="email", type="text", nullable=False, default="''")
        assert emitter.column_definition(col) == '"email" text NOT NULL DEFAULT \'\''

    @pytest.mark.parametrize(
        "source_type, raw_default, expected",
        [
            # MSSQL date/time functions translate to PG equivalents.
            ("datetime", "(getdate())", "now()"),
            ("datetime2", "(GETDATE())", "now()"),
            ("datetime2", "(sysdatetime())", "LOCALTIMESTAMP"),
            ("datetime2", "(getutcdate())", "(now() AT TIME ZONE 'utc')"),
            ("datetime2", "(sysutcdatetime())", "(now() AT TIME ZONE 'utc')"),
            # uuid generators.
            ("uniqueidentifier", "(newid())", "gen_random_uuid()"),
            ("uniqueidentifier", "(newsequentialid())", "gen_random_uuid()"),
            # session info.
            ("varchar", "(suser_sname())", "CURRENT_USER"),
            ("varchar", "(db_name())", "current_database()"),
            # ``N'foo'`` unicode literal → plain literal.
            ("varchar", "(N'foo')", "'foo'"),
            # ``bit`` → boolean coercion of 0/1 literals.
            ("bit", "((0))", "FALSE"),
            ("bit", "((1))", "TRUE"),
            # Double parens around integer literal — peel both.
            ("int", "((42))", "42"),
            # Already PG-friendly expression: must be left untouched.
            ("int", "1 + 1", "1 + 1"),
            # Unbalanced wrapping must not be peeled.
            ("int", "(1)+(2)", "(1)+(2)"),
            # Oracle bare keywords (no parens).
            ("date", "SYSDATE", "now()"),
            ("timestamp", "SYSTIMESTAMP", "now()"),
            ("varchar", "USER", "CURRENT_USER"),
            # Oracle SYS_GUID() and MySQL UUID().
            ("uniqueidentifier", "SYS_GUID()", "gen_random_uuid()"),
            ("uniqueidentifier", "uuid()", "gen_random_uuid()"),
            # MySQL bit default literal on a boolean-mapped column.
            ("bit", "b'0'", "FALSE"),
            ("bit", "b'1'", "TRUE"),
            # PG-compatible keywords must survive untouched.
            ("timestamp", "CURRENT_TIMESTAMP", "CURRENT_TIMESTAMP"),
            ("date", "CURRENT_DATE", "CURRENT_DATE"),
        ],
    )
    def test_default_translation(
        self, source_type: str, raw_default: str, expected: str
    ) -> None:
        emitter = PostgresSqlEmitter(preserve_case=True)
        col = Column(name="c", type=source_type, default=raw_default)
        definition = emitter.column_definition(col)
        assert definition.endswith(f"DEFAULT {expected}"), definition


class TestEmitSchemasAndTables:
    def _db(self) -> Database:
        db = Database(name="main")
        public = Schema(name="public")
        author = Table(name="author")
        author.add_column(
            Column(name="id", type="int", identity=True, constraint="PRIMARY KEY")
        )
        author.add_column(Column(name="name", type="text", nullable=False))
        public.add_table(author)
        db.add_schema(public)
        return db

    def test_emit_schemas_uses_mapping_and_dedup(self) -> None:
        emitter = PostgresSqlEmitter(
            preserve_case=True, schema_mapping={"dbo": "public"}
        )
        db = Database(name="main")
        db.add_schema(Schema(name="dbo"))
        db.add_schema(Schema(name="other"))
        sink = _Sink()
        emitter.emit_schemas(db, sink)
        assert sink.text.count("CREATE SCHEMA IF NOT EXISTS") == 2
        assert '"public"' in sink.text
        assert '"other"' in sink.text

    def test_emit_tables_emits_primary_key(self) -> None:
        emitter = PostgresSqlEmitter(preserve_case=True)
        sink = _Sink()
        emitter.emit_tables(self._db(), sink)
        assert 'CREATE TABLE "public"."author"' in sink.text
        assert "PRIMARY KEY (\"id\")" in sink.text

    def test_emit_foreign_keys_skips_dangling_refs(self) -> None:
        emitter = PostgresSqlEmitter(preserve_case=True)
        db = self._db()
        # Add a book table referencing a missing target schema
        book = Table(name="book")
        book.add_column(Column(name="author_id", type="int"))
        book.add_foreign_key(ForeignKey("missing", "author", ("author_id",), ("id",)))
        db.schemas["public"].add_table(book)

        sink = _Sink()
        emitter.emit_foreign_keys(db, sink)
        assert "ALTER TABLE" not in sink.text  # dangling FK is silently skipped

    def test_emit_foreign_keys_with_valid_reference(self) -> None:
        emitter = PostgresSqlEmitter(preserve_case=True)
        db = self._db()
        book = Table(name="book")
        book.add_column(Column(name="author_id", type="int"))
        book.add_foreign_key(ForeignKey("public", "author", ("author_id",), ("id",)))
        db.schemas["public"].add_table(book)
        sink = _Sink()
        emitter.emit_foreign_keys(db, sink)
        assert 'ALTER TABLE "public"."book"' in sink.text
        assert 'REFERENCES "public"."author" ("id")' in sink.text

    def test_emit_foreign_keys_keeps_composite_key_in_one_statement(self) -> None:
        emitter = PostgresSqlEmitter(preserve_case=True)
        db = self._db()
        vote = Table(name="vote")
        vote.add_column(Column(name="author_id", type="int"))
        vote.add_column(Column(name="state", type="char"))
        vote.add_foreign_key(
            ForeignKey("public", "author", ("author_id", "state"), ("id", "state"))
        )
        db.schemas["public"].add_table(vote)
        sink = _Sink()
        emitter.emit_foreign_keys(db, sink)
        # One statement per constraint: split per column, each half would point
        # at a non-unique key and the target would reject it.
        assert sink.text.count("ALTER TABLE") == 1
        assert 'ADD FOREIGN KEY ("author_id", "state")' in sink.text
        assert 'REFERENCES "public"."author" ("id", "state")' in sink.text

    def test_emit_indexes(self) -> None:
        emitter = PostgresSqlEmitter(preserve_case=True)
        db = self._db()
        db.schemas["public"].tables["author"].add_index("idx_name", "name")
        sink = _Sink()
        emitter.emit_indexes(db, sink)
        assert 'CREATE INDEX "idx_name" ON "public"."author" ("name")' in sink.text

    def test_emit_schemas_dedups_mapped_collisions(self) -> None:
        emitter = PostgresSqlEmitter(
            preserve_case=True, schema_mapping={"dbo": "public", "audit": "public"}
        )
        db = Database(name="main")
        db.add_schema(Schema(name="dbo"))
        db.add_schema(Schema(name="audit"))
        sink = _Sink()
        emitter.emit_schemas(db, sink)
        assert sink.text.count("CREATE SCHEMA IF NOT EXISTS") == 1

    def test_emit_drops_emits_in_reverse_dependency_order(self) -> None:
        emitter = PostgresSqlEmitter(preserve_case=True)
        db = self._db()
        book = Table(name="book")
        book.add_column(Column(name="author_id", type="int"))
        book.add_foreign_key(ForeignKey("public", "author", ("author_id",), ("id",)))
        db.schemas["public"].add_table(book)

        sink = _Sink()
        emitter.emit_drops(db, sink)

        text = sink.text
        assert 'DROP TABLE IF EXISTS "public"."book";' in text
        assert 'DROP TABLE IF EXISTS "public"."author";' in text
        # child must be dropped before parent
        assert text.index('"public"."book"') < text.index('"public"."author"')

    def test_emit_drops_respects_schema_mapping(self) -> None:
        emitter = PostgresSqlEmitter(
            preserve_case=True, schema_mapping={"dbo": "public"}
        )
        db = Database(name="main")
        dbo = Schema(name="dbo")
        dbo.add_table(Table(name="author"))
        db.add_schema(dbo)
        sink = _Sink()
        emitter.emit_drops(db, sink)
        assert 'DROP TABLE IF EXISTS "public"."author";' in sink.text

    def test_emit_drops_on_empty_database_writes_only_trailing_newline(self) -> None:
        emitter = PostgresSqlEmitter(preserve_case=True)
        sink = _Sink()
        emitter.emit_drops(Database(name="main"), sink)
        assert "DROP TABLE" not in sink.text

    def test_emit_truncates_uses_single_comma_separated_statement(self) -> None:
        emitter = PostgresSqlEmitter(preserve_case=True)
        db = self._db()
        book = Table(name="book")
        book.add_column(Column(name="author_id", type="int"))
        book.add_foreign_key(ForeignKey("public", "author", ("author_id",), ("id",)))
        db.schemas["public"].add_table(book)
        sink = _Sink()
        emitter.emit_truncates(db, sink)
        text = sink.text
        assert text.count("TRUNCATE TABLE") == 1
        assert '"public"."author"' in text
        assert '"public"."book"' in text
        assert "RESTART IDENTITY" in text

    def test_emit_truncates_on_empty_database_writes_nothing(self) -> None:
        emitter = PostgresSqlEmitter(preserve_case=True)
        sink = _Sink()
        emitter.emit_truncates(Database(name="main"), sink)
        assert sink.text == ""

    def test_emit_truncates_respects_schema_mapping(self) -> None:
        emitter = PostgresSqlEmitter(
            preserve_case=True, schema_mapping={"dbo": "public"}
        )
        db = Database(name="main")
        dbo = Schema(name="dbo")
        dbo.add_table(Table(name="author"))
        db.add_schema(dbo)
        sink = _Sink()
        emitter.emit_truncates(db, sink)
        assert '"public"."author"' in sink.text

    def test_emit_foreign_keys_skips_when_ref_table_missing(self) -> None:
        emitter = PostgresSqlEmitter(preserve_case=True)
        db = self._db()
        # schema exists but the referenced table does not
        book = Table(name="book")
        book.add_column(Column(name="author_id", type="int"))
        book.add_foreign_key(ForeignKey("public", "no_such_table", ("author_id",), ("id",)))
        db.schemas["public"].add_table(book)
        sink = _Sink()
        emitter.emit_foreign_keys(db, sink)
        assert "ALTER TABLE" not in sink.text


class TestRowFormatting:
    def _table(self) -> tuple[Schema, Table]:
        schema = Schema(name="public")
        table = Table(name="t")
        table.add_column(Column(name="id", type="int"))
        table.add_column(Column(name="name", type="text"))
        return schema, table

    def test_copy_format_handles_null_bool_bytes_and_escapes(self) -> None:
        emitter = PostgresSqlEmitter(preserve_case=True)
        schema, table = self._table()
        rows = [
            (None, "plain"),
            (True, "tab\there"),
            (False, "new\nline"),
            (1, b"\x00\x01\x02"),
            (2, "back\\slash"),
        ]
        sink = _Sink()
        emitter.emit_data_copy(schema, table, rows, sink)
        text = sink.text
        assert "\\N\tplain" in text
        assert "t\ttab\\there" in text
        assert "f\tnew\\nline" in text
        assert "\\\\x000102" in text
        assert "back\\\\slash" in text
        assert text.rstrip().endswith("\\.")

    def test_insert_format_escapes_single_quotes_and_handles_types(self) -> None:
        emitter = PostgresSqlEmitter(preserve_case=True)
        schema, table = self._table()
        rows = [
            (None, "Bob"),
            (1, "O'Reilly"),
            (2, b"\x00"),
            (3, True),
        ]
        sink = _Sink()
        emitter.emit_data_insert(schema, table, rows, sink)
        text = sink.text
        assert "VALUES (NULL, 'Bob');" in text
        assert "VALUES (1, 'O''Reilly');" in text
        assert "VALUES (2, '\\x00');" in text
        assert "VALUES (3, TRUE);" in text
