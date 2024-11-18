"""DumpDatabaseUseCase orchestration tests focused on view materialization."""

from __future__ import annotations

from typing import Any, Iterable, Iterator, List, Tuple

import pytest

from db2sql.application.dto import (
    ColumnOverrideOption,
    DataFormat,
    DumpOptions,
    DumpRequest,
    ViewExportRequest,
)
from db2sql.application.use_cases import DumpDatabaseUseCase
from db2sql.domain.model import Column, Database, Schema, Table
from db2sql.domain.policy import FilterRules


class _Sink:
    def __init__(self) -> None:
        self.parts: List[str] = []

    def write(self, data: str) -> None:
        self.parts.append(data)

    def boundary(self) -> None:
        pass


class _Logger:
    def __init__(self) -> None:
        self.info_messages: List[str] = []

    def trace(self, message: str) -> None: ...

    def debug(self, message: str) -> None: ...

    def info(self, message: str) -> None:
        self.info_messages.append(message)

    def warning(self, message: str) -> None: ...

    def error(self, message: str) -> None: ...


class _Reader:
    """Fake SourceReader that supports both real-table and query paths."""

    def __init__(
        self,
        database: Database,
        view_columns: dict[str, List[Column]] | None = None,
        view_rows: dict[str, List[Tuple[Any, ...]]] | None = None,
    ) -> None:
        self._database = database
        self._view_columns = view_columns or {}
        self._view_rows = view_rows or {}
        self.iter_calls: List[Tuple[str, str, int]] = []
        self.describe_calls: List[str] = []
        self.query_iter_calls: List[Tuple[str, int]] = []

    def collect_metadata(self) -> Database:
        return self._database

    def iter_rows(
        self, schema: str, table: Table, limit: int = -1
    ) -> Iterator[Tuple[Any, ...]]:
        self.iter_calls.append((schema, table.name, limit))
        yield (1, "row")

    def describe_query(self, query: str) -> List[Column]:
        self.describe_calls.append(query)
        return [Column(name=c.name, type=c.type, nullable=c.nullable) for c in self._view_columns[query]]

    def iter_query_rows(
        self, query: str, limit: int = -1
    ) -> Iterator[Tuple[Any, ...]]:
        self.query_iter_calls.append((query, limit))
        for row in self._view_rows.get(query, []):
            yield row


class _Emitter:
    def __init__(self) -> None:
        self.calls: List[str] = []
        self.tables_seen: List[Tuple[str, str, List[str]]] = []
        self.copy_calls: List[Tuple[str, str, List[Tuple[Any, ...]]]] = []
        self.insert_calls: List[Tuple[str, str, List[Tuple[Any, ...]]]] = []

    def emit_prologue(self, sink: Any) -> None:
        self.calls.append("prologue")

    def emit_epilogue(self, sink: Any) -> None:
        self.calls.append("epilogue")

    def emit_schemas(self, database: Database, sink: Any) -> None:
        self.calls.append("schemas")

    def emit_tables(self, database: Database, sink: Any) -> None:
        self.calls.append("tables")
        for schema in database.schemas.values():
            for table in schema.tables.values():
                self.tables_seen.append(
                    (schema.name, table.name, list(table.columns))
                )

    def emit_foreign_keys(self, database: Database, sink: Any) -> None:
        self.calls.append("foreign_keys")

    def emit_indexes(self, database: Database, sink: Any) -> None:
        self.calls.append("indexes")

    def emit_data_copy(
        self,
        schema: Schema,
        table: Table,
        rows: Iterable[Iterable[Any]],
        sink: Any,
    ) -> None:
        materialized = [tuple(r) for r in rows]
        self.copy_calls.append((schema.name, table.name, materialized))

    def emit_data_insert(
        self,
        schema: Schema,
        table: Table,
        rows: Iterable[Iterable[Any]],
        sink: Any,
    ) -> None:
        materialized = [tuple(r) for r in rows]
        self.insert_calls.append((schema.name, table.name, materialized))


def _empty_db() -> Database:
    db = Database(name="main")
    db.add_schema(Schema(name="public"))
    return db


def _db_with_author() -> Database:
    db = _empty_db()
    author = Table(name="author")
    author.add_column(Column(name="id", type="int", constraint="PRIMARY KEY"))
    db.schemas["public"].add_table(author)
    return db


def _run(
    *,
    database: Database,
    reader: _Reader,
    request: DumpRequest,
) -> Tuple[_Emitter, _Sink, _Logger, Database]:
    emitter = _Emitter()
    sink = _Sink()
    logger = _Logger()
    materialized = DumpDatabaseUseCase(
        reader=reader, emitter=emitter, sink=sink, logger=logger, request=request,
    ).execute()
    return emitter, sink, logger, materialized


class TestViewMaterialization:
    def test_view_is_attached_as_synthetic_table(self) -> None:
        db = _db_with_author()
        view_query = "SELECT id, name FROM author"
        reader = _Reader(
            db,
            view_columns={
                view_query: [
                    Column(name="id", type="integer", nullable=False),
                    Column(name="name", type="text", nullable=True),
                ]
            },
            view_rows={view_query: [(1, "Alice"), (2, "Bob")]},
        )
        request = DumpRequest(
            options=DumpOptions(),
            filter_rules=FilterRules(),
            views=(
                ViewExportRequest(
                    key="author_names",
                    query=view_query,
                    target_schema="public",
                    target_table="author_names",
                ),
            ),
        )

        emitter, _, _, _ = _run(database=db, reader=reader, request=request)

        # The view's synthetic table appears alongside the real one in the emit pass.
        assert ("public", "author_names", ["id", "name"]) in emitter.tables_seen
        # Data came via iter_query_rows, not iter_rows.
        assert reader.describe_calls == [view_query]
        assert reader.query_iter_calls == [(view_query, -1)]
        # Real-table data path is still used for the original table.
        assert ("public", "author", -1) in reader.iter_calls

    def test_view_data_is_emitted_via_iter_query_rows(self) -> None:
        db = _empty_db()
        view_query = "SELECT 1 AS n"
        reader = _Reader(
            db,
            view_columns={view_query: [Column(name="n", type="integer", nullable=False)]},
            view_rows={view_query: [(1,), (2,), (3,)]},
        )
        request = DumpRequest(
            options=DumpOptions(),
            filter_rules=FilterRules(),
            views=(
                ViewExportRequest(
                    key="numbers",
                    query=view_query,
                    target_schema="public",
                    target_table="numbers",
                ),
            ),
        )

        emitter, _, _, _ = _run(database=db, reader=reader, request=request)
        assert emitter.copy_calls == [("public", "numbers", [(1,), (2,), (3,)])]

    def test_view_data_format_override_routes_to_insert(self) -> None:
        db = _empty_db()
        view_query = "SELECT 1 AS n"
        reader = _Reader(
            db,
            view_columns={view_query: [Column(name="n", type="integer")]},
            view_rows={view_query: [(7,)]},
        )
        request = DumpRequest(
            options=DumpOptions(default_data_format=DataFormat.COPY),
            filter_rules=FilterRules(),
            views=(
                ViewExportRequest(
                    key="v",
                    query=view_query,
                    target_schema="public",
                    target_table="v",
                    data_format=DataFormat.INSERT,
                ),
            ),
        )

        emitter, _, _, _ = _run(database=db, reader=reader, request=request)
        assert emitter.copy_calls == []
        assert emitter.insert_calls == [("public", "v", [(7,)])]

    def test_view_limit_is_forwarded_to_iter_query_rows(self) -> None:
        db = _empty_db()
        view_query = "SELECT * FROM t"
        reader = _Reader(
            db,
            view_columns={view_query: [Column(name="x", type="integer")]},
            view_rows={view_query: [(i,) for i in range(10)]},
        )
        request = DumpRequest(
            options=DumpOptions(),
            filter_rules=FilterRules(),
            views=(
                ViewExportRequest(
                    key="v",
                    query=view_query,
                    target_schema="public",
                    target_table="v",
                    limit_records=3,
                ),
            ),
        )
        _run(database=db, reader=reader, request=request)
        assert reader.query_iter_calls == [(view_query, 3)]

    def test_target_schema_is_created_if_missing(self) -> None:
        db = _empty_db()  # only "public"
        view_query = "SELECT 1 AS n"
        reader = _Reader(
            db,
            view_columns={view_query: [Column(name="n", type="integer")]},
            view_rows={view_query: []},
        )
        request = DumpRequest(
            options=DumpOptions(),
            filter_rules=FilterRules(),
            views=(
                ViewExportRequest(
                    key="v",
                    query=view_query,
                    target_schema="reporting",
                    target_table="v",
                ),
            ),
        )
        emitter, _, _, _ = _run(database=db, reader=reader, request=request)
        assert ("reporting", "v", ["n"]) in emitter.tables_seen

    def test_overrides_replace_inferred_types(self) -> None:
        db = _empty_db()
        view_query = "SELECT id, total FROM t"
        reader = _Reader(
            db,
            view_columns={
                view_query: [
                    Column(name="id", type="text"),     # inferred wrong, will be overridden
                    Column(name="total", type="text"),  # ditto
                ]
            },
            view_rows={view_query: []},
        )
        request = DumpRequest(
            options=DumpOptions(),
            filter_rules=FilterRules(),
            views=(
                ViewExportRequest(
                    key="v",
                    query=view_query,
                    target_schema="public",
                    target_table="v",
                    column_overrides={
                        "id": ColumnOverrideOption(type="integer", nullable=False),
                        "total": ColumnOverrideOption(
                            type="numeric", precision=10, scale=2
                        ),
                    },
                ),
            ),
        )
        _, _, _, materialized = _run(database=db, reader=reader, request=request)
        table = materialized.schemas["public"].tables["v"]
        assert table.columns["id"].type == "integer"
        assert table.columns["id"].nullable is False
        assert table.columns["total"].type == "numeric"
        assert table.columns["total"].precision == 10
        assert table.columns["total"].scale == 2

    def test_primary_key_marks_columns_and_unsets_nullable(self) -> None:
        db = _empty_db()
        view_query = "SELECT id FROM t"
        reader = _Reader(
            db,
            view_columns={view_query: [Column(name="id", type="integer", nullable=True)]},
            view_rows={view_query: []},
        )
        request = DumpRequest(
            options=DumpOptions(),
            filter_rules=FilterRules(),
            views=(
                ViewExportRequest(
                    key="v",
                    query=view_query,
                    target_schema="public",
                    target_table="v",
                    primary_key=("id",),
                ),
            ),
        )
        _, _, _, materialized = _run(database=db, reader=reader, request=request)
        col = materialized.schemas["public"].tables["v"].columns["id"]
        assert col.constraint == "PRIMARY KEY"
        assert col.is_primary_key is True
        assert col.nullable is False

    def test_unknown_primary_key_column_raises_value_error(self) -> None:
        db = _empty_db()
        view_query = "SELECT 1 AS id"
        reader = _Reader(
            db,
            view_columns={view_query: [Column(name="id", type="integer")]},
            view_rows={view_query: []},
        )
        request = DumpRequest(
            options=DumpOptions(),
            filter_rules=FilterRules(),
            views=(
                ViewExportRequest(
                    key="v",
                    query=view_query,
                    target_schema="public",
                    target_table="v",
                    primary_key=("missing",),
                ),
            ),
        )
        with pytest.raises(ValueError, match="primary_key references unknown column"):
            _run(database=db, reader=reader, request=request)

    def test_indexes_are_carried_over_to_synthetic_table(self) -> None:
        db = _empty_db()
        view_query = "SELECT x FROM t"
        reader = _Reader(
            db,
            view_columns={view_query: [Column(name="x", type="integer")]},
            view_rows={view_query: []},
        )
        request = DumpRequest(
            options=DumpOptions(),
            filter_rules=FilterRules(),
            views=(
                ViewExportRequest(
                    key="v",
                    query=view_query,
                    target_schema="public",
                    target_table="v",
                    indexes={"idx_x": ("x",)},
                ),
            ),
        )
        _, _, _, materialized = _run(database=db, reader=reader, request=request)
        assert materialized.schemas["public"].tables["v"].indexes == {"idx_x": ["x"]}

    def test_no_views_does_not_call_describe_or_iter_query(self) -> None:
        db = _db_with_author()
        reader = _Reader(db)
        request = DumpRequest(options=DumpOptions(), filter_rules=FilterRules())
        _run(database=db, reader=reader, request=request)
        assert reader.describe_calls == []
        assert reader.query_iter_calls == []
