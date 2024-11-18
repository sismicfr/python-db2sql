"""YAML schema SourceReader.

The reader expects a YAML file with the following shape::

    schemas:
      public:
        tables:
          users:
            columns:
              - { name: id,    type: integer, primary_key: true }
              - { name: email, type: varchar, length: 255 }
            rows:
              - [1, "alice@example.com"]
              - [2, "bob@example.com"]

Useful for documentation pipelines, fixtures, or smoke-testing other emitters
without a live database.

Configuration::

    driver: yaml
    server:
      options:
        path: ./schema.yml
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Iterator, List, Tuple

import yaml

from db2sql.application.ports import Logger
from db2sql.domain.model import Column, Database, ForeignKey, Schema, Table
from db2sql.infrastructure.config import AppConfig
from db2sql.infrastructure.persistence.errors import SourceReaderError


class YamlSchemaReader:
    """Load a hand-written YAML description of a database."""

    def __init__(self, config: AppConfig, logger: Logger) -> None:
        self._config = config
        self._logger = logger
        path = config.server.options.get("path") or config.server.dbname
        if not path:
            raise SourceReaderError("YAML reader requires server.options.path")
        self._path = Path(path)
        self._data: dict[str, Any] = {}

    def _load(self) -> dict[str, Any]:
        if self._data:
            return self._data
        if not self._path.is_file():
            raise SourceReaderError(f"YAML schema not found: {self._path}")
        self._logger.info(f"loading YAML schema: {self._path}")
        with self._path.open("r", encoding="utf-8") as stream:
            self._data = yaml.safe_load(stream) or {}
        return self._data

    def collect_metadata(self) -> Database:
        data = self._load()
        database = Database(self._path.stem)
        for schema_name, schema_def in (data.get("schemas") or {}).items():
            schema = Schema(schema_name)
            database.add_schema(schema)
            for table_name, table_def in (schema_def.get("tables") or {}).items():
                table = Table(table_name)
                for col_def in table_def.get("columns") or []:
                    column = Column(
                        name=col_def["name"],
                        type=col_def.get("type", "text"),
                        nullable=col_def.get("nullable", True),
                        char_length=col_def.get("length", -1),
                        default=col_def.get("default"),
                    )
                    if col_def.get("primary_key"):
                        column.constraint = "PRIMARY KEY"
                        column.nullable = False
                    fk = col_def.get("foreign_key")
                    if fk:
                        column.foreign_key = ForeignKey(
                            schema=fk.get("schema", schema_name),
                            table=fk["table"],
                            column=fk["column"],
                        )
                    table.add_column(column)
                database.add_table(schema_name, table)
        return database

    def iter_rows(
        self, schema: str, table: Table, limit: int = -1
    ) -> Iterator[Tuple[Any, ...]]:
        data = self._load()
        rows: List[List[Any]] = (
            (data.get("schemas") or {})
            .get(schema, {})
            .get("tables", {})
            .get(table.name, {})
            .get("rows", [])
        )
        for index, row in enumerate(rows):
            if 0 <= limit <= index:
                return
            yield tuple(row)


def build_reader(config: AppConfig, logger: Logger) -> YamlSchemaReader:
    """Entry-point factory."""
    return YamlSchemaReader(config, logger)
