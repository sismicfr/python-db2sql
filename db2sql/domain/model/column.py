"""Column entity."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

from .foreign_key import ForeignKey


@dataclass
class Column:
    """Describes a single column. Populated by infrastructure readers."""

    name: str
    type: str
    default: Optional[str] = None
    nullable: bool = False
    char_length: int = -1
    precision: Optional[int] = None
    scale: Optional[int] = None
    computed_definition: Optional[str] = None
    identity: bool = False
    constraint: Optional[str] = None
    foreign_key: Optional[ForeignKey] = None

    @property
    def is_primary_key(self) -> bool:
        return self.constraint == "PRIMARY KEY"
