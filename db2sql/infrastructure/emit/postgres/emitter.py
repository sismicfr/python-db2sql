"""PostgreSQL emitter implementing the application SqlEmitter port."""

from __future__ import annotations

import re
from typing import Any, Dict, Iterable, Mapping, Optional

from db2sql.application.ports import OutputSink
from db2sql.domain.model import Column, Database, Schema, Table
from db2sql.domain.policy import (
    drop_order,
    normalize_identifier,
    resolve_schema_name,
    topological_order,
)

# Source-side scalar functions that have no PG equivalent under the same name.
# Keys are lowercased, parens stripped; values are PG expressions to substitute.
# Matched regardless of whether the source wrote them with empty parens
# (``getdate()``) or as bare keywords (Oracle ``SYSDATE``).
_DEFAULT_FUNCTION_MAP: Dict[str, str] = {
    # MSSQL date/time
    "getdate": "now()",
    "sysdatetime": "LOCALTIMESTAMP",
    "getutcdate": "(now() AT TIME ZONE 'utc')",
    "sysutcdatetime": "(now() AT TIME ZONE 'utc')",
    "sysdatetimeoffset": "now()",
    # Oracle date/time (bare keywords, no parens)
    "sysdate": "now()",
    "systimestamp": "now()",
    # MSSQL / Oracle / MySQL uuid generators
    "newid": "gen_random_uuid()",
    "newsequentialid": "gen_random_uuid()",
    "sys_guid": "gen_random_uuid()",
    "uuid": "gen_random_uuid()",
    # Session info — MSSQL / Oracle
    "suser_sname": "CURRENT_USER",
    "system_user": "CURRENT_USER",
    "user_name": "CURRENT_USER",
    "user": "CURRENT_USER",
    "db_name": "current_database()",
}

_UNICODE_STRING_RE = re.compile(r"(?i)\bN'")
_FUNCTION_CALL_RE = re.compile(r"^\s*([A-Za-z_][A-Za-z0-9_]*)(?:\s*\(\s*\))?\s*$")
# MySQL ``bit`` default literal — ``b'0'`` / ``b'1'``.
_MYSQL_BIT_RE = re.compile(r"^(?i:b)'([01]+)'$")

# Largest decimal precision each PG integer type can hold *in full*: any
# ``precision``-digit value fits, with room to spare. smallint tops out at
# 32767 (5 digits, not all of them), integer at 2147483647 (10 digits),
# bigint at 9223372036854775807 (19 digits) — hence 4 / 9 / 18.
_INTEGER_PRECISION_LIMITS = ((4, "smallint"), (9, "integer"), (18, "bigint"))


def _integer_type_for(precision: int) -> Optional[str]:
    """Return the narrowest integer type that holds any ``precision``-digit value.

    ``None`` when no integer type is wide enough, i.e. above 18 digits: those
    have to stay ``numeric`` or the migration would silently overflow.
    """
    for limit, name in _INTEGER_PRECISION_LIMITS:
        if precision <= limit:
            return name
    return None


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
        escaped = normalized.replace('"', '""')
        return f'"{escaped}"'

    def schema_name(self, schema: Schema) -> str:
        mapped = resolve_schema_name(self._schema_mapping, schema.name)
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
            # An explicit scale of 0 means the source stores integers in a
            # decimal type — the common MSSQL / Oracle ``NUMBER(n)`` pattern.
            # Promote to a native integer so identity columns can become
            # serial/bigserial and FK types line up with referencing tables.
            # A scale of None means "unknown", not "zero": leave those alone.
            if column.scale == 0:
                promoted = _integer_type_for(column.precision)
                if promoted is not None:
                    return promoted
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
            parts.append(f"DEFAULT {self._translate_default(column.default, target_type)}")
        return " ".join(parts)

    @staticmethod
    def _strip_wrapping_parens(expr: str) -> str:
        # MSSQL wraps every default in at least one extra pair of parens
        # (``((0))``, ``(getdate())``, ``(N'foo')``). Peel only when the outer
        # pair encloses the whole expression — leave ``(1)+(2)`` alone.
        expr = expr.strip()
        while expr.startswith("(") and expr.endswith(")"):
            depth = 0
            balanced = True
            for index, ch in enumerate(expr):
                if ch == "(":
                    depth += 1
                elif ch == ")":
                    depth -= 1
                    if depth == 0 and index != len(expr) - 1:
                        balanced = False
                        break
            if not balanced:
                break
            expr = expr[1:-1].strip()
        return expr

    def _translate_default(self, raw: str, target_type: str) -> str:
        expr = self._strip_wrapping_parens(raw)

        # ``N'foo'`` → ``'foo'``. PG has no N-prefixed string literal; strings
        # are already unicode-capable.
        expr = _UNICODE_STRING_RE.sub("'", expr)

        # ``0`` / ``1`` → ``FALSE`` / ``TRUE`` when the column maps to boolean
        # (MSSQL ``bit`` becomes PG ``boolean`` and PG won't coerce int→bool
        # inside a DEFAULT clause). MySQL ``bit`` defaults arrive as ``b'1'``.
        if target_type == "boolean":
            if expr in ("0", "1"):
                return "FALSE" if expr == "0" else "TRUE"
            bit_match = _MYSQL_BIT_RE.match(expr)
            if bit_match:
                return "FALSE" if int(bit_match.group(1), 2) == 0 else "TRUE"

        match = _FUNCTION_CALL_RE.match(expr)
        if match:
            fn = match.group(1).lower()
            replacement = _DEFAULT_FUNCTION_MAP.get(fn)
            if replacement is not None:
                return replacement

        return expr

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
            target = resolve_schema_name(self._schema_mapping, schema.name)
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
                for constraint in table.foreign_key_constraints:
                    ref_schema = database.schemas.get(constraint.ref_schema)
                    if ref_schema is None:
                        continue
                    ref_table = ref_schema.get_table(constraint.ref_table)
                    if ref_table is None:
                        continue
                    ref_qualified = self.table_name(ref_schema, ref_table)
                    columns = ", ".join(self.quote_identifier(c) for c in constraint.columns)
                    ref_columns = ", ".join(
                        self.quote_identifier(c) for c in constraint.ref_columns
                    )
                    sink.write(
                        f"ALTER TABLE {qualified} "
                        f"ADD FOREIGN KEY ({columns}) "
                        f"REFERENCES {ref_qualified} ({ref_columns});\n"
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
