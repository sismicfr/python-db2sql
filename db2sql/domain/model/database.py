"""Database aggregate root."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, Optional

from db2sql.domain.errors import DuplicatedSchemaError

from .schema import Schema
from .table import Table


@dataclass
class Database:
    """Collected metadata for a database: the aggregate root."""

    name: str
    schemas: Dict[str, Schema] = field(default_factory=dict)

    def add_schema(self, schema: Schema) -> None:
        if schema.name in self.schemas:
            raise DuplicatedSchemaError(schema.name)
        self.schemas[schema.name] = schema

    def get_schema(self, name: str) -> Optional[Schema]:
        return self.schemas.get(name)

    def add_table(self, schema: str, table: Table) -> None:
        target = self.schemas.get(schema)
        if target is not None:
            target.add_table(table)

    def get_table(self, schema: str, table: str) -> Optional[Table]:
        target = self.schemas.get(schema)
        if target is None:
            return None
        return target.get_table(table)
