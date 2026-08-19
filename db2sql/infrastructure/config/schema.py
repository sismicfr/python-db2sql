"""Pydantic v2 configuration schema (infrastructure-only)."""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

from pydantic import BaseModel, ConfigDict, Field, field_validator

from db2sql.application.dto import DataFormat


class ServerConfig(BaseModel):
    """Connection parameters for the source database."""

    model_config = ConfigDict(extra="forbid")

    hostname: Optional[str] = None
    port: Optional[int] = None
    username: Optional[str] = None
    password: Optional[str] = None
    dbname: Optional[str] = None
    dsn: Optional[str] = None
    options: Dict[str, str] = Field(default_factory=dict)

    def fields_shadowed_by_dsn(self) -> Tuple[str, ...]:
        """Discrete connection fields that ``dsn`` makes irrelevant.

        A DSN replaces the whole connection rather than merging with it, so
        anything set alongside it is silently unused. Callers report this back
        to the user instead of letting the mismatch pass unnoticed.
        """
        if not self.dsn:
            return ()
        return tuple(
            name for name in _DISCRETE_CONNECTION_FIELDS if getattr(self, name) is not None
        )


_DISCRETE_CONNECTION_FIELDS = ("hostname", "port", "username", "password", "dbname")


class TableOverride(BaseModel):
    """Per-table overrides applied on top of the global dump options."""

    model_config = ConfigDict(extra="forbid")

    data_format: Optional[DataFormat] = None
    limit_records: Optional[int] = None
    where: Optional[str] = None


class ColumnOverride(BaseModel):
    """Override an inferred column's type metadata for a view export."""

    model_config = ConfigDict(extra="forbid")

    type: Optional[str] = None
    nullable: Optional[bool] = None
    char_length: Optional[int] = None
    precision: Optional[int] = None
    scale: Optional[int] = None


class ViewExport(BaseModel):
    """A custom-query export, materialized in the dump as a synthesized table.

    The result of ``query`` is treated like a regular table: its schema is
    inferred from the result set (one probe row), then merged with any
    per-column overrides declared in ``columns``.
    """

    model_config = ConfigDict(extra="forbid")

    query: str
    target_schema: Optional[str] = None
    target_table: Optional[str] = None
    data_format: Optional[DataFormat] = None
    limit_records: Optional[int] = None
    columns: Dict[str, ColumnOverride] = Field(default_factory=dict)
    primary_key: List[str] = Field(default_factory=list)
    indexes: Dict[str, List[str]] = Field(default_factory=dict)


class DumpConfig(BaseModel):
    """Global dump options."""

    model_config = ConfigDict(extra="forbid")

    preserve_case: bool = False
    limit_records: int = -1
    default_data_format: DataFormat = DataFormat.COPY
    include_schemas: List[str] = Field(default_factory=list)
    exclude_schemas: List[str] = Field(default_factory=list)
    include_tables: List[str] = Field(default_factory=list)
    exclude_tables: List[str] = Field(default_factory=list)
    mapping_schemas: Dict[str, str] = Field(default_factory=dict)
    tables: Dict[str, TableOverride] = Field(default_factory=dict)
    views: Dict[str, ViewExport] = Field(default_factory=dict)
    on_existing: str = "fail"
    use_transaction: bool = True

    @field_validator("on_existing", mode="before")
    @classmethod
    def _validate_on_existing(cls, value: Any) -> Any:
        if value is None:
            return "fail"
        if value not in ("fail", "drop", "truncate"):
            raise ValueError("dump.on_existing must be one of 'fail', 'drop', 'truncate'")
        return value

    @field_validator(
        "include_schemas", "exclude_schemas", "include_tables", "exclude_tables", mode="before"
    )
    @classmethod
    def _flatten_str_lists(cls, value: Any) -> Any:
        """Accept argparse-style nested lists (``[["a", "b"], ["c"]]``)."""
        if value is None:
            return []
        if isinstance(value, str):
            return [item.strip() for item in value.split(",") if item.strip()]
        if isinstance(value, list):
            out: List[str] = []
            for item in value:
                if isinstance(item, list):
                    out.extend(str(sub) for sub in item)
                elif isinstance(item, str):
                    out.extend(part.strip() for part in item.split(",") if part.strip())
                else:
                    out.append(str(item))
            return out
        return value


class MigrateConfig(BaseModel):
    """Options specific to the live ``migrate`` subcommand."""

    model_config = ConfigDict(extra="forbid")

    on_existing: str = "fail"
    transaction_mode: str = "single"
    batch_size: int = 1000
    use_transaction: bool = True

    @field_validator("on_existing", mode="before")
    @classmethod
    def _validate_on_existing(cls, value: Any) -> Any:
        if value is None:
            return "fail"
        if value not in ("fail", "drop", "truncate"):
            raise ValueError("migrate.on_existing must be one of 'fail', 'drop', 'truncate'")
        return value


class AppConfig(BaseModel):
    """Root db2sql configuration."""

    model_config = ConfigDict(extra="forbid")

    driver: str = "mssql"
    target: str = "postgres"
    server: ServerConfig = Field(default_factory=ServerConfig)
    target_server: ServerConfig = Field(default_factory=ServerConfig)
    dump: DumpConfig = Field(default_factory=DumpConfig)
    migrate: MigrateConfig = Field(default_factory=MigrateConfig)
    output_file: Optional[str] = None
    split_size: Optional[int] = None
