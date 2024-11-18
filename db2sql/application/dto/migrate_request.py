"""DTO consumed by :class:`MigrateDatabaseUseCase`."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Tuple

from db2sql.domain.policy import FilterRules

from .dump_request import DumpOptions, OnExisting, ViewExportRequest

__all__ = ["MigrateRequest", "OnExisting", "TransactionMode"]


class TransactionMode(str, Enum):
    """Granularity of the wrapping transaction(s)."""

    SINGLE = "single"
    PER_TABLE = "per_table"


@dataclass(frozen=True)
class MigrateRequest:
    """Aggregate request for a live database-to-database migration.

    Mirrors :class:`DumpRequest` so that the use case stays nearly identical;
    the only difference is the chosen sink/writer pair on the infrastructure
    side. ``options`` and ``filter_rules`` are reused unchanged from the dump
    pipeline to guarantee that dump and migrate produce the same DDL.
    """

    options: DumpOptions
    filter_rules: FilterRules
    views: Tuple[ViewExportRequest, ...] = ()
    on_existing: OnExisting = OnExisting.FAIL
    transaction_mode: TransactionMode = TransactionMode.SINGLE
    batch_size: int = 1000
    use_transaction: bool = True
