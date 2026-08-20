"""Turn per-column catalog rows into one foreign key per constraint.

Every catalog reports foreign keys one row per column, so a composite key
arrives as several rows sharing a constraint name. Each reader collects those
rows in position order and hands them here.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Iterable, List, Optional, Tuple

from db2sql.domain.model import Database, ForeignKey


@dataclass(frozen=True)
class ForeignKeyColumn:
    """A single ``(local column -> referenced column)`` row from a catalog.

    ``key`` groups rows belonging to the same constraint; it is usually the
    constraint name, but any value the catalog provides will do (SQLite, for
    instance, only numbers its foreign keys).
    """

    schema: str
    table: str
    key: str
    column: str
    ref_schema: str
    ref_table: str
    ref_column: str
    name: Optional[str] = None


def attach_foreign_keys(database: Database, rows: Iterable[ForeignKeyColumn]) -> None:
    """Group ``rows`` by constraint and attach the result to their tables.

    Rows must already be in the constraint's column order — local and
    referenced columns are paired positionally. A constraint is skipped when
    its table or any of its columns is absent from ``database`` (excluded
    schema, filtered table).
    """
    grouped: Dict[Tuple[str, str, str], List[ForeignKeyColumn]] = {}
    for row in rows:
        grouped.setdefault((row.schema, row.table, row.key), []).append(row)

    for (schema, table_name, _), members in grouped.items():
        table = database.get_table(schema, table_name)
        if table is None:
            continue
        if any(table.get_column(member.column) is None for member in members):
            continue
        first = members[0]
        table.add_foreign_key(
            ForeignKey(
                schema=first.ref_schema,
                table=first.ref_table,
                columns=tuple(member.column for member in members),
                ref_columns=tuple(member.ref_column for member in members),
                name=first.name,
            )
        )
