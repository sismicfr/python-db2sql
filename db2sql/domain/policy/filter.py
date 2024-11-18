"""Pure filtering policy: produce a new Database keeping only selected schemas/tables."""

from __future__ import annotations

import copy
from dataclasses import dataclass, field
from typing import FrozenSet

from db2sql.domain.model import Database


@dataclass(frozen=True)
class FilterRules:
    """Rules controlling which schemas/tables to keep when emitting."""

    include_schemas: FrozenSet[str] = field(default_factory=frozenset)
    exclude_schemas: FrozenSet[str] = field(default_factory=frozenset)
    include_tables: FrozenSet[str] = field(default_factory=frozenset)
    exclude_tables: FrozenSet[str] = field(default_factory=frozenset)

    def table_included(self, schema: str, table: str) -> bool:
        if self.exclude_schemas and schema in self.exclude_schemas:
            return False
        if self.include_schemas and schema not in self.include_schemas:
            return False
        full = f"{schema}.{table}"
        if self.exclude_tables and (table in self.exclude_tables or full in self.exclude_tables):
            return False
        if self.include_tables and not (
            table in self.include_tables or full in self.include_tables
        ):
            return False
        return True


def filter_database(database: Database, rules: FilterRules) -> Database:
    """Return a deep copy of ``database`` keeping only schemas/tables that match ``rules``."""
    pruned = copy.deepcopy(database)
    for schema_name in list(pruned.schemas):
        schema = pruned.schemas[schema_name]
        for table_name in list(schema.tables):
            if not rules.table_included(schema_name, table_name):
                del schema.tables[table_name]
        if not schema.tables:
            del pruned.schemas[schema_name]
    return pruned
