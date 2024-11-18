"""Use case: dump a source database into a target-dialect SQL stream."""

from __future__ import annotations

from typing import Optional

from db2sql.application.dto import (
    DataFormat,
    DumpOptions,
    DumpRequest,
    OnExisting,
    ViewExportRequest,
)
from db2sql.application.ports import Logger, OutputSink, SourceReader, SqlEmitter
from db2sql.domain.model import Database
from db2sql.domain.policy import filter_database

from .materialize_views import materialize_views


class DumpDatabaseUseCase:
    """Walks the source DB and writes a SQL dump using only the injected ports."""

    def __init__(
        self,
        reader: SourceReader,
        emitter: SqlEmitter,
        sink: OutputSink,
        logger: Logger,
        request: DumpRequest,
    ) -> None:
        self._reader = reader
        self._emitter = emitter
        self._sink = sink
        self._logger = logger
        self._request = request

    def execute(self) -> Database:
        database = self._reader.collect_metadata()
        database = filter_database(database, self._request.filter_rules)
        if self._request.views:
            self._logger.info(
                f"materializing {len(self._request.views)} view export(s)"
            )
            materialize_views(self._reader, database, self._request.views)
        self._emit(database)
        return database

    def _emit(self, database: Database) -> None:
        sink = self._sink
        if self._request.use_transaction:
            self._emitter.emit_prologue(sink)
        if self._request.on_existing is OnExisting.TRUNCATE:
            # Data-only mode: assume the schema already exists on the target.
            # Skip DDL entirely and just TRUNCATE then reload.
            self._emitter.emit_truncates(database, sink)
            self._emit_data(database)
        else:
            self._emitter.emit_schemas(database, sink)
            if self._request.on_existing is OnExisting.DROP:
                self._emitter.emit_drops(database, sink)
            self._emitter.emit_tables(database, sink)
            self._emit_data(database)
            self._emitter.emit_foreign_keys(database, sink)
            self._emitter.emit_indexes(database, sink)
        if self._request.use_transaction:
            self._emitter.emit_epilogue(sink)

    def _emit_data(self, database: Database) -> None:
        options = self._request.options
        view_options = {
            (v.target_schema, v.target_table): v for v in self._request.views
        }
        for schema_name, schema in database.schemas.items():
            for table_name, table in schema.tables.items():
                view = view_options.get((schema_name, table_name))
                fmt = self._resolve_format(view, options, schema_name, table_name)
                limit = self._resolve_limit(view, options, schema_name, table_name)
                if limit == 0:
                    continue
                self._logger.info(
                    f"dumping rows from {schema_name}.{table_name} ({fmt.value})"
                )
                if table.source_query is not None:
                    rows = self._reader.iter_query_rows(table.source_query, limit=limit)
                else:
                    rows = self._reader.iter_rows(schema_name, table, limit=limit)
                if fmt is DataFormat.COPY:
                    self._emitter.emit_data_copy(schema, table, rows, self._sink)
                else:
                    self._emitter.emit_data_insert(schema, table, rows, self._sink)

    @staticmethod
    def _resolve_format(
        view: Optional[ViewExportRequest],
        options: DumpOptions,
        schema_name: str,
        table_name: str,
    ) -> DataFormat:
        if view is not None and view.data_format is not None:
            return view.data_format
        return options.resolve_data_format(schema_name, table_name)

    @staticmethod
    def _resolve_limit(
        view: Optional[ViewExportRequest],
        options: DumpOptions,
        schema_name: str,
        table_name: str,
    ) -> int:
        if view is not None and view.limit_records is not None:
            return view.limit_records
        return options.resolve_limit(schema_name, table_name)
