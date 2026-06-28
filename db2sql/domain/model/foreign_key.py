"""Foreign key value objects."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Tuple


@dataclass(frozen=True)
class ForeignKey:
    """Reference to another column. Immutable value object."""

    schema: str
    table: str
    column: str


@dataclass(frozen=True)
class ForeignKeyConstraint:
    """A named FK constraint grouping one or more columns. Immutable value object."""

    name: str
    ref_schema: str
    ref_table: str
    columns: Tuple[str, ...]
    ref_columns: Tuple[str, ...]
