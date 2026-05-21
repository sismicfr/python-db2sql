"""Domain layer: entities and pure policies. No infrastructure dependency."""

from .errors import (
    DomainError,
    DuplicatedColumnError,
    DuplicatedItemError,
    DuplicatedSchemaError,
    DuplicatedTableError,
)
from .model import Column, Database, ForeignKey, Schema, Table
from .policy import filter_database, FilterRules, normalize_identifier, to_snake_case

__all__ = [
    "Column",
    "Database",
    "DomainError",
    "DuplicatedColumnError",
    "DuplicatedItemError",
    "DuplicatedSchemaError",
    "DuplicatedTableError",
    "FilterRules",
    "ForeignKey",
    "Schema",
    "Table",
    "filter_database",
    "normalize_identifier",
    "to_snake_case",
]
