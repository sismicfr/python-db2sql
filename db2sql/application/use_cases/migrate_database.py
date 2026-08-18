"""Use case: migrate a source database directly into a live target database.

The orchestration mirrors :class:`DumpDatabaseUseCase` so the DDL-identity
invariant holds: the same emitter methods are called in the same order,
producing the same SQL strings — except that here the strings go to an
``ExecutingSink`` backed by a ``TargetWriter`` instead of a text file.

Row data takes a different path on purpose: ``writer.bulk_load`` uses the
target's fastest native bulk-load primitive (``COPY FROM STDIN`` for
PostgreSQL, ``executemany`` for MSSQL, ...). The state produced in the target
DB is equivalent to what ``psql -f dump.sql`` would have produced.
"""

from __future__ import annotations

from typing import Optional

from db2sql.application.dto import (
    DumpOptions,
    MigrateRequest,
    OnExisting,
    ViewExportRequest,
)
from db2sql.application.ports import (
    Logger,
    OutputSink,
    SourceReader,
    SqlEmitter,
    TargetWriter,
)
from db2sql.domain.model import Database
from db2sql.domain.policy import filter_database, resolve_schema_name

from .materialize_views import materialize_views


class MigrateDatabaseUseCase:
    """Walks the source DB and writes DDL + data into a live target DB."""

    def __init__(
        self,
        reader: SourceReader,
        emitter: SqlEmitter,
        sink: OutputSink,
        writer: TargetWriter,
        logger: Logger,
        request: MigrateRequest,
    ) -> None:
        self._reader = reader
        self._emitter = emitter
        self._sink = sink
        self._writer = writer
        self._logger = logger
        self._request = request

    def execute(self) -> Database:
        database = self._reader.collect_metadata()
        database = filter_database(database, self._request.filter_rules)
        if self._request.views:
            self._logger.info(f"materializing {len(self._request.views)} view export(s)")
            materialize_views(self._reader, database, self._request.views)
        self._emit_and_load(database)
        return database

    def _emit_and_load(self, database: Database) -> None:
        sink = self._sink
        if self._request.use_transaction:
            self._emitter.emit_prologue(sink)
        if self._request.on_existing is OnExisting.TRUNCATE:
            self._emitter.emit_truncates(database, sink)
            self._load_data(database)
        else:
            self._emitter.emit_schemas(database, sink)
            if self._request.on_existing is OnExisting.DROP:
                self._emitter.emit_drops(database, sink)
            self._emitter.emit_tables(database, sink)
            self._load_data(database)
            self._emitter.emit_foreign_keys(database, sink)
            self._emitter.emit_indexes(database, sink)
        if self._request.use_transaction:
            self._emitter.emit_epilogue(sink)

    def _load_data(self, database: Database) -> None:
        options = self._request.options
        view_options = {(v.target_schema, v.target_table): v for v in self._request.views}
        for schema_name, schema in database.schemas.items():
            for table_name, table in schema.tables.items():
                view = view_options.get((schema_name, table_name))
                limit = self._resolve_limit(view, options, schema_name, table_name)
                if limit == 0:
                    continue
                self._logger.info(f"bulk-loading rows into {schema_name}.{table_name}")
                if table.source_query is not None:
                    rows = self._reader.iter_query_rows(table.source_query, limit=limit)
                else:
                    rows = self._reader.iter_rows(schema_name, table, limit=limit)
                # Rows go to the schema the DDL just created, not the source one.
                target_schema = resolve_schema_name(options.mapping_schemas, schema_name)
                self._writer.bulk_load(target_schema, table, rows)

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
