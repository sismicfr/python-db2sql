"""Foreign key value object."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ForeignKey:
    """Reference to another column. Immutable value object."""

    schema: str
    table: str
    column: str
