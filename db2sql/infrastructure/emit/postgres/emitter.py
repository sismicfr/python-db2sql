"""PostgreSQL emitter implementing the application SqlEmitter port."""

from __future__ import annotations

from typing import Any, Dict, Iterable, Mapping, Optional

from db2sql.application.ports import OutputSink
from db2sql.domain.model import Column, Database, Schema, Table
from db2sql.domain.policy import drop_order, normalize_identifier, topological_order


class PostgresSqlEmitter:
    """Produce PostgreSQL DDL+DML for a collected :class:`Database`."""

    DEFAULT_TYPE_MAP: Dict[str, str] = {
        # numeric
        "bit": "boolean",
        "boolean": "boolean",
        "tinyint": "smallint",
        "smallint": "smallint",
        "int": "integer",
        "integer": "integer",
        "mediumint": "integer",
        "bigint": "bigint",
        "real": "real",
        "float": "double precision",
        "double": "double precision",
        "numeric": "numeric",
        "decimal": "numeric",
        "money": "numeric(19,4)",
        "smallmoney": "numeric(10,4)",
        "number": "numeric",
        "binary_float": "real",
        "binary_double": "double precision",
        # text
        "char": "char",
        "nchar": "char",
        "varchar": "varchar",
        "varchar2": "varchar",
        "nvarchar": "varchar",
        "nvarchar2": "varchar",
        "text": "text",
        "ntext": "text",
        "clob": "text",
        "nclob": "text",
        "long": "text",
        "longtext": "text",
        "mediumtext": "text",
        # binary
        "binary": "bytea",
        "varbinary": "bytea",
        "blob": "bytea",
        "bfile": "bytea",
        "raw": "bytea",
        "long raw": "bytea",
        "image": "bytea",
        # date / time
        "date": "date",
        "time": "time",
        "datetime": "timestamp",
        "datetime2": "timestamp",
        "smalldatetime": "timestamp",
        "timestamp": "timestamp",
        "timestamp with time zone": "timestamptz",
        "timestamp with local time zone": "timestamptz",
        "datetimeoffset": "timestamptz",
        # misc
        "uniqueidentifier": "uuid",
        "rowid": "text",
        "urowid": "text",
        "json": "jsonb",
        "jsonb": "jsonb",
        "xml": "xml",
        "xmltype": "xml",
    }

    def __init__(
        self,
        preserve_case: bool = False,
        schema_mapping: Optional[Mapping[str, str]] = None,
    ) -> None:
        self._preserve_case = preserve_case
        self._schema_mapping: Mapping[str, str] = schema_mapping or {}
        self._type_map: Mapping[str, str] = dict(self.DEFAULT_TYPE_MAP)

    # ---- identifier helpers -------------------------------------------------

    def _normalize(self, name: str) -> str:
        return normalize_identifier(name, self._preserve_case)

    def quote_identifier(self, name: str) -> str:
        normalized = self._normalize(name)
        return '"{}"'.format(normalized.replace('"', '""'))

    def schema_name(self, schema: Schema) -> str:
        mapped = self._schema_mapping.get(schema.name, schema.name)
        return self.quote_identifier(mapped)

    def table_name(self, schema: Schema, table: Table) -> str:
        return f"{self.schema_name(schema)}.{self.quote_identifier(table.name)}"

    def _map_type(self, column: Column) -> str:
        source = (column.type or "text").lower()
        target = self._type_map.get(source, source)
        if target.startswith("char") or target.startswith("varchar"):
            if column.char_length and column.char_length > 0:
                return f"{target}({column.char_length})"
        if target == "numeric" and column.precision:
            scale = column.scale or 0
            return f"numeric({column.precision},{scale})"
        return target

    def column_definition(self, column: Column) -> str:
        target_type = self._map_type(column)
        if column.identity:
            target_type = "serial" if target_type in ("integer", "smallint") else "bigserial"
        parts = [self.quote_identifier(column.name), target_type]
        if not column.nullable and not column.identity:
            parts.append("NOT NULL")
        if column.default is not None and not column.identity:
            parts.append(f"DEFAULT {column.default}")
        return " ".join(parts)

    # ---- emit -------------------------------------------------------------

    def emit_prologue(self, sink: OutputSink) -> None:
        sink.write("BEGIN;\n\n")
        sink.boundary()

    def emit_epilogue(self, sink: OutputSink) -> None:
        sink.write("COMMIT;\n")
        sink.boundary()

    def emit_schemas(self, database: Database, sink: OutputSink) -> None:
        emitted = set()
        for schema in database.schemas.values():
            target = self._schema_mapping.get(schema.name, schema.name)
            if target in emitted:
                continue
            emitted.add(target)
            sink.write(f"CREATE SCHEMA IF NOT EXISTS {self.quote_identifier(target)};\n")
            sink.boundary()
        sink.write("\n")

    def emit_drops(self, database: Database, sink: OutputSink) -> None:
        for schema_name, table_name in drop_order(database):
            schema = database.schemas[schema_name]
            table = schema.get_table(table_name)
            if table is None:
                continue
            qualified = self.table_name(schema, table)
            sink.write(f"DROP TABLE IF EXISTS {qualified};\n")
            sink.boundary()
        sink.write("\n")

    def emit_truncates(self, database: Database, sink: OutputSink) -> None:
        # Single TRUNCATE with comma-separated tables — atomic, resolves FK
        # between listed tables without CASCADE. Order is irrelevant inside the
        # list; we use topological order for stable, readable output.
        qualified_names = []
        for schema_name, table_name in topological_order(database):
            schema = database.schemas[schema_name]
            table = schema.get_table(table_name)
            if table is None:
                continue
            qualified_names.append(self.table_name(schema, table))
        if not qualified_names:
            return
        joined = ", ".join(qualified_names)
        sink.write(f"TRUNCATE TABLE {joined} RESTART IDENTITY;\n\n")
        sink.boundary()

    def emit_tables(self, database: Database, sink: OutputSink) -> None:
        for schema in database.schemas.values():
            for table in schema.tables.values():
                qualified = self.table_name(schema, table)
                sink.write(f"CREATE TABLE {qualified} (\n")
                column_lines = [
                    f"    {self.column_definition(col)}" for col in table.columns.values()
                ]
                pk_cols = table.primary_key_columns()
                if pk_cols:
                    quoted = ", ".join(self.quote_identifier(c) for c in pk_cols)
                    column_lines.append(f"    PRIMARY KEY ({quoted})")
                sink.write(",\n".join(column_lines))
                sink.write("\n);\n\n")
                sink.boundary()

    def emit_foreign_keys(self, database: Database, sink: OutputSink) -> None:
        for schema in database.schemas.values():
            for table in schema.tables.values():
                qualified = self.table_name(schema, table)
                for column in table.columns.values():
                    fk = column.foreign_key
                    if not fk:
                        continue
                    ref_schema = database.schemas.get(fk.schema)
                    if ref_schema is None:
                        continue
                    ref_table = ref_schema.get_table(fk.table)
                    if ref_table is None:
                        continue
                    ref_qualified = self.table_name(ref_schema, ref_table)
                    sink.write(
                        f"ALTER TABLE {qualified} "
                        f"ADD FOREIGN KEY ({self.quote_identifier(column.name)}) "
                        f"REFERENCES {ref_qualified} "
                        f"({self.quote_identifier(fk.column)});\n"
                    )
                    sink.boundary()
        sink.write("\n")

    def emit_indexes(self, database: Database, sink: OutputSink) -> None:
        for schema in database.schemas.values():
            for table in schema.tables.values():
                qualified = self.table_name(schema, table)
                for index_name, columns in table.indexes.items():
                    cols = ", ".join(self.quote_identifier(c) for c in columns)
                    sink.write(
                        f"CREATE INDEX {self.quote_identifier(index_name)} "
                        f"ON {qualified} ({cols});\n"
                    )
                    sink.boundary()
        sink.write("\n")

    @staticmethod
    def _format_copy_value(value: Any) -> str:
        if value is None:
            return r"\N"
        if isinstance(value, bool):
            return "t" if value else "f"
        if isinstance(value, (bytes, bytearray)):
            return "\\\\x" + bytes(value).hex()
        text = str(value)
        return (
            text.replace("\\", "\\\\")
            .replace("\t", "\\t")
            .replace("\n", "\\n")
            .replace("\r", "\\r")
        )

    @staticmethod
    def _format_insert_value(value: Any) -> str:
        if value is None:
            return "NULL"
        if isinstance(value, bool):
            return "TRUE" if value else "FALSE"
        if isinstance(value, (int, float)):
            return str(value)
        if isinstance(value, (bytes, bytearray)):
            return "'\\x" + bytes(value).hex() + "'"
        escaped = str(value).replace("'", "''")
        return f"'{escaped}'"

    def emit_data_copy(
        self,
        schema: Schema,
        table: Table,
        rows: Iterable[Iterable[Any]],
        sink: OutputSink,
    ) -> None:
        qualified = self.table_name(schema, table)
        columns = ", ".join(self.quote_identifier(c) for c in table.columns)
        sink.write(f"COPY {qualified} ({columns}) FROM stdin;\n")
        for row in rows:
            sink.write("\t".join(self._format_copy_value(v) for v in row))
            sink.write("\n")
        sink.write("\\.\n\n")
        sink.boundary()

    def emit_data_insert(
        self,
        schema: Schema,
        table: Table,
        rows: Iterable[Iterable[Any]],
        sink: OutputSink,
    ) -> None:
        qualified = self.table_name(schema, table)
        columns = ", ".join(self.quote_identifier(c) for c in table.columns)
        for row in rows:
            values = ", ".join(self._format_insert_value(v) for v in row)
            sink.write(f"INSERT INTO {qualified} ({columns}) VALUES ({values});\n")
            sink.boundary()
        sink.write("\n")
