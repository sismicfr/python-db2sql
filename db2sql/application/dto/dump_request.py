"""Application-level DTOs that the use case consumes.

The use case never sees Pydantic, YAML, or CLI args. The infrastructure
``config.mapper`` translates the raw config into these immutable DTOs.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, FrozenSet, Mapping, Optional, Tuple

from db2sql.domain.policy import FilterRules

from .data_format import DataFormat


class OnExisting(str, Enum):
    """Strategy when a target object already exists.

    ``TRUNCATE`` is only meaningful for ``migrate`` mode; ``dump`` mode rejects
    it at configuration time because the dump recreates every table from
    scratch.
    """

    FAIL = "fail"
    DROP = "drop"
    TRUNCATE = "truncate"


@dataclass(frozen=True)
class TableOption:
    """Per-table overrides resolved by the mapper, keyed by ``schema.table`` or ``table``."""

    data_format: Optional[DataFormat] = None
    limit_records: Optional[int] = None


@dataclass(frozen=True)
class ColumnOverrideOption:
    """Per-column override applied after inferring a view's schema from a probe row."""

    type: Optional[str] = None
    nullable: Optional[bool] = None
    char_length: Optional[int] = None
    precision: Optional[int] = None
    scale: Optional[int] = None


@dataclass(frozen=True)
class ViewExportRequest:
    """A custom-query export, surfaced as a synthesized table in the dump."""

    key: str
    query: str
    target_schema: str
    target_table: str
    data_format: Optional[DataFormat] = None
    limit_records: Optional[int] = None
    column_overrides: Mapping[str, ColumnOverrideOption] = field(default_factory=dict)
    primary_key: Tuple[str, ...] = ()
    indexes: Mapping[str, Tuple[str, ...]] = field(default_factory=dict)


@dataclass(frozen=True)
class DumpOptions:
    """Global dump options, decoupled from the infrastructure configuration shape."""

    preserve_case: bool = False
    limit_records: int = -1
    default_data_format: DataFormat = DataFormat.COPY
    mapping_schemas: Mapping[str, str] = field(default_factory=dict)
    table_options: Mapping[str, TableOption] = field(default_factory=dict)

    def resolve_data_format(self, schema: str, table: str) -> DataFormat:
        override = self._override_for(schema, table)
        if override is not None and override.data_format is not None:
            return override.data_format
        return self.default_data_format

    def resolve_limit(self, schema: str, table: str) -> int:
        override = self._override_for(schema, table)
        if override is not None and override.limit_records is not None:
            return override.limit_records
        return self.limit_records

    def _override_for(self, schema: str, table: str) -> Optional[TableOption]:
        for key in (f"{schema}.{table}", table):
            override = self.table_options.get(key)
            if override is not None:
                return override
        return None


@dataclass(frozen=True)
class DumpRequest:
    """Aggregate request passed to the use case."""

    options: DumpOptions
    filter_rules: FilterRules
    output_file: Optional[str] = None
    views: Tuple[ViewExportRequest, ...] = ()
    split_size: Optional[int] = None
    on_existing: OnExisting = OnExisting.FAIL
    use_transaction: bool = True
