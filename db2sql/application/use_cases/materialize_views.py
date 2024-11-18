"""Materialize configured view exports as synthesized tables on the Database."""

from __future__ import annotations

from typing import Iterable, List, Mapping

from db2sql.application.dto import ColumnOverrideOption, ViewExportRequest
from db2sql.application.ports import SourceReader
from db2sql.domain.model import Column, Database, Schema, Table


def materialize_views(
    reader: SourceReader,
    database: Database,
    views: Iterable[ViewExportRequest],
) -> None:
    """Attach a synthesized :class:`Table` for each view to ``database``.

    The columns are inferred via ``reader.describe_query`` then merged with the
    user-supplied per-column overrides. Primary-key columns listed in the view
    request are flagged accordingly so the emitter renders a PRIMARY KEY clause.
    """
    for view in views:
        columns = reader.describe_query(view.query)
        columns = _apply_overrides(columns, view.column_overrides)
        _apply_primary_key(columns, view.primary_key)
        table = Table(
            name=view.target_table,
            columns={col.name: col for col in columns},
            indexes={name: list(cols) for name, cols in view.indexes.items()},
            source_query=view.query,
        )
        schema = database.get_schema(view.target_schema)
        if schema is None:
            schema = Schema(view.target_schema)
            database.add_schema(schema)
        schema.add_table(table)


def _apply_overrides(
    columns: List[Column],
    overrides: Mapping[str, ColumnOverrideOption],
) -> List[Column]:
    if not overrides:
        return columns
    for column in columns:
        override = overrides.get(column.name)
        if override is None:
            continue
        if override.type is not None:
            column.type = override.type
        if override.nullable is not None:
            column.nullable = override.nullable
        if override.char_length is not None:
            column.char_length = override.char_length
        if override.precision is not None:
            column.precision = override.precision
        if override.scale is not None:
            column.scale = override.scale
    return columns


def _apply_primary_key(columns: List[Column], primary_key: Iterable[str]) -> None:
    pk = tuple(primary_key)
    if not pk:
        return
    by_name = {col.name: col for col in columns}
    for name in pk:
        column = by_name.get(name)
        if column is None:
            raise ValueError(
                f"primary_key references unknown column '{name}' in view export"
            )
        column.constraint = "PRIMARY KEY"
        column.nullable = False
