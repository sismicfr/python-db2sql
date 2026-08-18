"""Domain entities — pure Python, no infrastructure dependency."""

from .column import Column
from .database import Database
from .foreign_key import ForeignKey, ForeignKeyConstraint
from .schema import Schema
from .table import Table

__all__ = ["Column", "Database", "ForeignKey", "ForeignKeyConstraint", "Schema", "Table"]
