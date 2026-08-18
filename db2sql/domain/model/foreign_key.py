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
    """A named FK constraint, spanning one or more columns.

    ``columns`` and ``ref_columns`` are ordered by the constraint's ordinal
    position and always have the same length, so ``columns[i]`` references
    ``ref_columns[i]``. Immutable value object.
    """

    name: str
    ref_schema: str
    ref_table: str
    columns: Tuple[str, ...]
    ref_columns: Tuple[str, ...]
