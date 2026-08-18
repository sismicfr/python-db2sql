"""Assembly of per-column catalog rows into named foreign-key constraints.

Every dialect exposes foreign keys as one row per participating column, so a
composite key spans several rows sharing a constraint name. Readers normalize
their catalog query into :class:`ForeignKeyColumn` rows and hand them here to be
grouped, which keeps the grouping rules identical across dialects.
"""

from __future__ import annotations

from typing import Dict, Iterable, List, NamedTuple, Tuple

from db2sql.domain.model import Column, Database, ForeignKey, ForeignKeyConstraint


class ForeignKeyColumn(NamedTuple):
    """One column of one foreign-key constraint, as read from the catalog."""

    constraint: str
    schema: str
    table: str
    column: str
    ref_schema: str
    ref_table: str
    ref_column: str


def attach_foreign_keys(database: Database, rows: Iterable[ForeignKeyColumn]) -> None:
    """Group ``rows`` into constraints and attach them to their table.

    Rows must arrive in ordinal-position order within a constraint — callers
    order their catalog query accordingly — since that order is what pairs each
    column with its referenced column.

    A constraint whose table is unknown, or that has a column missing from the
    collected model (filtered out, or belonging to an excluded table), is
    dropped: emitting a partial composite key would produce a constraint that
    does not match the source. Per-column :class:`ForeignKey` markers are still
    set on whatever columns resolve, because the drop/create ordering policy
    reads them.
    """
    groups: Dict[Tuple[str, str, str], List[ForeignKeyColumn]] = {}
    for row in rows:
        groups.setdefault((row.schema, row.table, row.constraint), []).append(row)

    for (schema_name, table_name, constraint_name), group in groups.items():
        table = database.get_table(schema_name, table_name)
        if table is None:
            continue
        resolved: List[Column] = []
        for row in group:
            column = table.get_column(row.column)
            if column is None:
                continue
            column.foreign_key = ForeignKey(row.ref_schema, row.ref_table, row.ref_column)
            resolved.append(column)
        if len(resolved) != len(group):
            continue
        table.foreign_key_constraints.append(
            ForeignKeyConstraint(
                name=constraint_name,
                ref_schema=group[0].ref_schema,
                ref_table=group[0].ref_table,
                columns=tuple(row.column for row in group),
                ref_columns=tuple(row.ref_column for row in group),
            )
        )
