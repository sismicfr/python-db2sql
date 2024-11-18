"""Schema entity."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, Optional

from db2sql.domain.errors import DuplicatedTableError

from .table import Table


@dataclass
class Schema:
    """Collected metadata for a single schema."""

    name: str
    tables: Dict[str, Table] = field(default_factory=dict)

    def add_table(self, table: Table) -> None:
        if table.name in self.tables:
            raise DuplicatedTableError(table.name)
        self.tables[table.name] = table

    def get_table(self, name: str) -> Optional[Table]:
        return self.tables.get(name)
