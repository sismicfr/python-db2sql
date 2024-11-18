"""Port for emitting target-dialect SQL from a collected database."""

from __future__ import annotations

from typing import Any, Iterable, Protocol

from db2sql.domain.model import Database, Schema, Table

from .output_sink import OutputSink


class SqlEmitter(Protocol):
    """Render a :class:`Database` aggregate as target-dialect SQL."""

    def emit_prologue(self, sink: OutputSink) -> None: ...

    def emit_epilogue(self, sink: OutputSink) -> None: ...

    def emit_schemas(self, database: Database, sink: OutputSink) -> None: ...

    def emit_drops(self, database: Database, sink: OutputSink) -> None: ...

    def emit_truncates(self, database: Database, sink: OutputSink) -> None: ...

    def emit_tables(self, database: Database, sink: OutputSink) -> None: ...

    def emit_foreign_keys(self, database: Database, sink: OutputSink) -> None: ...

    def emit_indexes(self, database: Database, sink: OutputSink) -> None: ...

    def emit_data_copy(
        self,
        schema: Schema,
        table: Table,
        rows: Iterable[Iterable[Any]],
        sink: OutputSink,
    ) -> None: ...

    def emit_data_insert(
        self,
        schema: Schema,
        table: Table,
        rows: Iterable[Iterable[Any]],
        sink: OutputSink,
    ) -> None: ...
