"""Table entity."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional

from db2sql.domain.errors import DuplicatedColumnError

from .column import Column


@dataclass
class Table:
    """Collected metadata for a single table."""

    name: str
    columns: Dict[str, Column] = field(default_factory=dict)
    indexes: Dict[str, List[str]] = field(default_factory=dict)
    source_query: Optional[str] = None

    def add_column(self, column: Column) -> None:
        if column.name in self.columns:
            raise DuplicatedColumnError(column.name)
        self.columns[column.name] = column

    def get_column(self, name: str) -> Optional[Column]:
        return self.columns.get(name)

    def add_index(self, index_name: str, column_name: str) -> None:
        self.indexes.setdefault(index_name, []).append(column_name)

    def primary_key_columns(self) -> List[str]:
        return [name for name, column in self.columns.items() if column.is_primary_key]
