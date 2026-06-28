"""Microsoft SQL Server emitter implementing the application SqlEmitter port."""

from __future__ import annotations

import warnings
from typing import Any, Dict, Iterable, Mapping, Optional

from db2sql.application.ports import OutputSink
from db2sql.domain.model import Column, Database, Schema, Table
from db2sql.domain.policy import drop_order, normalize_identifier


class MssqlSqlEmitter:
    """Produce Microsoft SQL Server DDL+DML for a collected :class:`Database`."""

    DEFAULT_TYPE_MAP: Dict[str, str] = {
        # numeric
        "bit": "bit",
        "boolean": "bit",
        "tinyint": "tinyint",
        "smallint": "smallint",
        "int": "int",
        "integer": "int",
        "mediumint": "int",
        "bigint": "bigint",
        "real": "real",
        "binary_float": "real",
        "float": "float",
        "double": "float",
        "double precision": "float",
        "binary_double": "float",
        "numeric": "numeric",
        "decimal": "numeric",
        "number": "numeric",
        "money": "money",
        "smallmoney": "smallmoney",
        # text
        "char": "nchar",
        "nchar": "nchar",
        "varchar": "nvarchar",
        "varchar2": "nvarchar",
        "nvarchar": "nvarchar",
        "nvarchar2": "nvarchar",
        "text": "nvarchar(max)",
        "ntext": "nvarchar(max)",
        "clob": "nvarchar(max)",
        "nclob": "nvarchar(max)",
        "long": "nvarchar(max)",
        "longtext": "nvarchar(max)",
        "mediumtext": "nvarchar(max)",
        # binary
        "binary": "varbinary",
        "varbinary": "varbinary",
        "blob": "varbinary(max)",
        "bfile": "varbinary(max)",
        "raw": "varbinary(max)",
        "long raw": "varbinary(max)",
        "image": "varbinary(max)",
        "bytea": "varbinary(max)",
        # date / time — MSSQL `timestamp` is a rowversion; map source timestamp → datetime2
        "date": "date",
        "time": "time",
        "datetime": "datetime2",
        "datetime2": "datetime2",
        "smalldatetime": "datetime2",
        "timestamp": "datetime2",
        "timestamp with time zone": "datetimeoffset",
        "timestamp with local time zone": "datetimeoffset",
        "datetimeoffset": "datetimeoffset",
        "timestamptz": "datetimeoffset",
        # misc — MSSQL has no native JSON type; nvarchar(max) is the canonical workaround
        "uniqueidentifier": "uniqueidentifier",
        "uuid": "uniqueidentifier",
        "rowid": "nvarchar(max)",
        "urowid": "nvarchar(max)",
        "json": "nvarchar(max)",
        "jsonb": "nvarchar(max)",
        "xml": "xml",
        "xmltype": "xml",
    }

    _SIZED_TEXT_PREFIXES = ("nchar", "nvarchar", "char", "varchar")
    _SIZED_BINARY_PREFIXES = ("binary", "varbinary")

    def __init__(
        self,
        preserve_case: bool = False,
        schema_mapping: Optional[Mapping[str, str]] = None,
    ) -> None:
        self._preserve_case = preserve_case
        self._schema_mapping: Mapping[str, str] = schema_mapping or {}
        self._type_map: Mapping[str, str] = dict(self.DEFAULT_TYPE_MAP)
        self._copy_warned = False

    # ---- identifier helpers -------------------------------------------------

    def _normalize(self, name: str) -> str:
        return normalize_identifier(name, self._preserve_case)

    def quote_identifier(self, name: str) -> str:
        normalized = self._normalize(name)
        return "[{}]".format(normalized.replace("]", "]]"))

    def schema_name(self, schema: Schema) -> str:
        mapped = self._schema_mapping.get(schema.name, self._schema_mapping.get("*", schema.name))
        return self.quote_identifier(mapped)

    def table_name(self, schema: Schema, table: Table) -> str:
        return f"{self.schema_name(schema)}.{self.quote_identifier(table.name)}"

    def _map_type(self, column: Column) -> str:
        source = (column.type or "nvarchar(max)").lower()
        target = self._type_map.get(source, source)
        if any(target == p for p in self._SIZED_TEXT_PREFIXES):
            if column.char_length and column.char_length > 0:
                return f"{target}({column.char_length})"
            return f"{target}(max)"
        if any(target == p for p in self._SIZED_BINARY_PREFIXES):
            if column.char_length and column.char_length > 0:
                return f"{target}({column.char_length})"
            return f"{target}(max)"
        if target == "numeric" and column.precision:
            scale = column.scale or 0
            return f"numeric({column.precision},{scale})"
        return target

    def column_definition(self, column: Column) -> str:
        target_type = self._map_type(column)
        parts = [self.quote_identifier(column.name), target_type]
        if column.identity:
            parts.append("IDENTITY(1,1)")
        if not column.nullable and not column.identity:
            parts.append("NOT NULL")
        if column.default is not None and not column.identity:
            parts.append(f"DEFAULT {column.default}")
        return " ".join(parts)

    # ---- emit -------------------------------------------------------------

    def emit_prologue(self, sink: OutputSink) -> None:
        sink.write("BEGIN TRANSACTION;\n\n")
        sink.boundary()

    def emit_epilogue(self, sink: OutputSink) -> None:
        sink.write("COMMIT TRANSACTION;\n")
        sink.boundary()

    def emit_schemas(self, database: Database, sink: OutputSink) -> None:
        emitted = set()
        for schema in database.schemas.values():
            target = self._schema_mapping.get(
                schema.name, self._schema_mapping.get("*", schema.name)
            )
            if target in emitted:
                continue
            emitted.add(target)
            quoted = self.quote_identifier(target)
            # CREATE SCHEMA must be the first statement in its batch — wrap in EXEC.
            literal = target.replace("'", "''")
            sink.write(
                f"IF NOT EXISTS (SELECT 1 FROM sys.schemas WHERE name = N'{literal}')\n"
                f"    EXEC('CREATE SCHEMA {quoted}');\n"
            )
            sink.boundary()
        sink.write("\n")

    def emit_drops(self, database: Database, sink: OutputSink) -> None:
        # Native ``DROP TABLE IF EXISTS`` syntax — requires SQL Server 2016+.
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
        # MSSQL has no multi-table TRUNCATE: emit one statement per table in
        # reverse-dependency order. DBCC CHECKIDENT (..., RESEED, 0) is only
        # appended when the table actually has an IDENTITY column — calling
        # it on a non-identity table raises an error on SQL Server.
        for schema_name, table_name in drop_order(database):
            schema = database.schemas[schema_name]
            table = schema.get_table(table_name)
            if table is None:
                continue
            qualified = self.table_name(schema, table)
            sink.write(f"TRUNCATE TABLE {qualified};\n")
            sink.boundary()
            if any(col.identity for col in table.columns.values()):
                literal = qualified.replace("'", "''")
                sink.write(f"DBCC CHECKIDENT ('{literal}', RESEED, 0);\n")
                sink.boundary()
        sink.write("\n")

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
                for fkc in table.foreign_key_constraints:
                    ref_schema = database.schemas.get(fkc.ref_schema)
                    if ref_schema is None:
                        continue
                    ref_table = ref_schema.get_table(fkc.ref_table)
                    if ref_table is None:
                        continue
                    ref_qualified = self.table_name(ref_schema, ref_table)
                    cols = ", ".join(self.quote_identifier(c) for c in fkc.columns)
                    ref_cols = ", ".join(self.quote_identifier(c) for c in fkc.ref_columns)
                    sink.write(
                        f"ALTER TABLE {qualified} "
                        f"ADD FOREIGN KEY ({cols}) "
                        f"REFERENCES {ref_qualified} ({ref_cols});\n"
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
    def _format_insert_value(value: Any) -> str:
        if value is None:
            return "NULL"
        if isinstance(value, bool):
            return "1" if value else "0"
        if isinstance(value, (int, float)):
            return str(value)
        if isinstance(value, (bytes, bytearray)):
            return "0x" + bytes(value).hex()
        escaped = str(value).replace("'", "''")
        return f"N'{escaped}'"

    def emit_data_copy(
        self,
        schema: Schema,
        table: Table,
        rows: Iterable[Iterable[Any]],
        sink: OutputSink,
    ) -> None:
        # MSSQL has no streaming COPY equivalent in plain T-SQL (BULK INSERT requires
        # a server-side file). Degrade to INSERT statements and warn the caller once.
        if not self._copy_warned:
            warnings.warn(
                "COPY is Postgres-only; falling back to INSERT for MSSQL output.",
                stacklevel=2,
            )
            self._copy_warned = True
        self.emit_data_insert(schema, table, rows, sink)

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
