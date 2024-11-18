"""SQLite SqlEmitter — produces SQL that can be loaded by ``sqlite3``.

Notable differences with the built-in PostgreSQL emitter:

* SQLite has no schemas — ``emit_schemas`` is a no-op and the table name is
  emitted without a schema prefix.
* Identifiers are quoted with double-quotes.
* ``INTEGER PRIMARY KEY`` is the canonical autoincrement form.
* SQLite has no ``COPY`` command, so ``emit_data_copy`` falls back to
  ``INSERT`` statements (wrapped in a single transaction by the prologue).
"""

from __future__ import annotations

from typing import Any, Dict, Iterable, Mapping, Optional

from db2sql.application.ports import OutputSink
from db2sql.domain.model import Column, Database, Schema, Table
from db2sql.domain.policy import normalize_identifier


class SqliteSqlEmitter:
    """Emit SQLite-flavoured DDL+DML for a collected :class:`Database`."""

    DEFAULT_TYPE_MAP: Dict[str, str] = {
        "bit": "INTEGER",
        "boolean": "INTEGER",
        "tinyint": "INTEGER",
        "smallint": "INTEGER",
        "int": "INTEGER",
        "integer": "INTEGER",
        "bigint": "INTEGER",
        "real": "REAL",
        "float": "REAL",
        "double": "REAL",
        "numeric": "NUMERIC",
        "decimal": "NUMERIC",
        "money": "NUMERIC",
        "char": "TEXT",
        "varchar": "TEXT",
        "nvarchar": "TEXT",
        "text": "TEXT",
        "clob": "TEXT",
        "json": "TEXT",
        "jsonb": "TEXT",
        "xml": "TEXT",
        "uuid": "TEXT",
        "date": "TEXT",
        "time": "TEXT",
        "datetime": "TEXT",
        "timestamp": "TEXT",
        "binary": "BLOB",
        "varbinary": "BLOB",
        "blob": "BLOB",
        "bytea": "BLOB",
    }

    def __init__(
        self,
        preserve_case: bool = False,
        schema_mapping: Optional[Mapping[str, str]] = None,
    ) -> None:
        self._preserve_case = preserve_case
        # schema_mapping is accepted for API compatibility but ignored:
        # SQLite has no schemas.
        self._schema_mapping = schema_mapping or {}
        self._type_map: Mapping[str, str] = dict(self.DEFAULT_TYPE_MAP)

    # ---- identifiers ------------------------------------------------------

    def _normalize(self, name: str) -> str:
        return normalize_identifier(name, self._preserve_case)

    def quote_identifier(self, name: str) -> str:
        normalized = self._normalize(name)
        return '"{}"'.format(normalized.replace('"', '""'))

    def _map_type(self, column: Column) -> str:
        source = (column.type or "text").lower()
        return self._type_map.get(source, "TEXT")

    def column_definition(self, column: Column, single_pk: bool) -> str:
        target_type = self._map_type(column)
        parts = [self.quote_identifier(column.name), target_type]
        if single_pk and column.is_primary_key:
            parts.append("PRIMARY KEY")
            if column.identity:
                parts.append("AUTOINCREMENT")
        if not column.nullable and not (single_pk and column.is_primary_key):
            parts.append("NOT NULL")
        if column.default is not None:
            parts.append(f"DEFAULT {column.default}")
        return " ".join(parts)

    # ---- emit -------------------------------------------------------------

    def emit_prologue(self, sink: OutputSink) -> None:
        sink.write("BEGIN TRANSACTION;\n\n")

    def emit_epilogue(self, sink: OutputSink) -> None:
        sink.write("COMMIT;\n")

    def emit_schemas(self, database: Database, sink: OutputSink) -> None:
        # SQLite has no schema concept — nothing to emit.
        return

    def emit_tables(self, database: Database, sink: OutputSink) -> None:
        for schema in database.schemas.values():
            for table in schema.tables.values():
                pk_cols = table.primary_key_columns()
                single_pk = len(pk_cols) == 1
                quoted = self.quote_identifier(table.name)
                sink.write(f"CREATE TABLE {quoted} (\n")
                lines = [
                    f"    {self.column_definition(col, single_pk)}"
                    for col in table.columns.values()
                ]
                if pk_cols and not single_pk:
                    quoted_cols = ", ".join(self.quote_identifier(c) for c in pk_cols)
                    lines.append(f"    PRIMARY KEY ({quoted_cols})")
                sink.write(",\n".join(lines))
                sink.write("\n);\n\n")

    def emit_foreign_keys(self, database: Database, sink: OutputSink) -> None:
        # SQLite does not support adding a FK via ALTER TABLE; foreign keys
        # would need to be inlined in CREATE TABLE. This emitter keeps things
        # simple and skips FKs, mirroring the spirit of the built-in MSSQL/PG
        # split where each emitter is free to drop unsupported features.
        return

    def emit_indexes(self, database: Database, sink: OutputSink) -> None:
        for schema in database.schemas.values():
            for table in schema.tables.values():
                quoted_table = self.quote_identifier(table.name)
                for index_name, columns in table.indexes.items():
                    cols = ", ".join(self.quote_identifier(c) for c in columns)
                    sink.write(
                        f"CREATE INDEX {self.quote_identifier(index_name)} "
                        f"ON {quoted_table} ({cols});\n"
                    )
        sink.write("\n")

    @staticmethod
    def _format_value(value: Any) -> str:
        if value is None:
            return "NULL"
        if isinstance(value, bool):
            return "1" if value else "0"
        if isinstance(value, (int, float)):
            return str(value)
        if isinstance(value, (bytes, bytearray)):
            return "x'" + bytes(value).hex() + "'"
        escaped = str(value).replace("'", "''")
        return f"'{escaped}'"

    def emit_data_copy(
        self,
        schema: Schema,
        table: Table,
        rows: Iterable[Iterable[Any]],
        sink: OutputSink,
    ) -> None:
        # SQLite has no COPY — fall back to INSERT.
        self.emit_data_insert(schema, table, rows, sink)

    def emit_data_insert(
        self,
        schema: Schema,
        table: Table,
        rows: Iterable[Iterable[Any]],
        sink: OutputSink,
    ) -> None:
        quoted_table = self.quote_identifier(table.name)
        columns = ", ".join(self.quote_identifier(c) for c in table.columns)
        for row in rows:
            values = ", ".join(self._format_value(v) for v in row)
            sink.write(f"INSERT INTO {quoted_table} ({columns}) VALUES ({values});\n")
        sink.write("\n")
