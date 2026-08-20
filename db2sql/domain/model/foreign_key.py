"""Foreign key value object."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, Tuple


@dataclass(frozen=True)
class ForeignKey:
    """One constraint: local columns referencing a key of another table.

    ``schema`` and ``table`` name the referenced table. ``columns`` and
    ``ref_columns`` are parallel: the n-th local column references the n-th
    referenced column. Composite keys are a single ForeignKey, not one per
    column — splitting them produces DDL the target rejects, since each half
    would point at a non-unique key.
    """

    schema: str
    table: str
    columns: Tuple[str, ...]
    ref_columns: Tuple[str, ...]
    name: Optional[str] = None

    def __post_init__(self) -> None:
        if not self.columns:
            raise ValueError("foreign key has no columns")
        if len(self.columns) != len(self.ref_columns):
            raise ValueError(
                f"foreign key column count mismatch: {self.columns} -> {self.ref_columns}"
            )
