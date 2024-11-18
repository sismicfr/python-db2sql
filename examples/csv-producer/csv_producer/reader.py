"""CSV-folder SourceReader.

Each ``*.csv`` file in the configured directory becomes a table. The first row
is treated as the column header; all columns are typed as ``text``. The first
column of each table is marked as the primary key.

Configuration (``db2sql.yml``)::

    driver: csv
    target: postgres
    server:
      options:
        path: ./sample_data    # required: directory holding the CSVs
        schema: public         # optional: target schema, defaults to "public"
        delimiter: ","         # optional, defaults to ","
"""

from __future__ import annotations

import csv
from pathlib import Path
from typing import Any, Iterator, Tuple

from db2sql.application.ports import Logger
from db2sql.domain.model import Column, Database, Schema, Table
from db2sql.infrastructure.config import AppConfig
from db2sql.infrastructure.persistence.errors import SourceReaderError

_DEFAULT_SCHEMA = "public"


class CsvFolderReader:
    """Treat each .csv file in a directory as a table."""

    def __init__(self, config: AppConfig, logger: Logger) -> None:
        self._config = config
        self._logger = logger
        opts = config.server.options
        self._root = Path(opts.get("path") or config.server.dbname or ".")
        self._schema = opts.get("schema", _DEFAULT_SCHEMA)
        self._delimiter = opts.get("delimiter", ",")

    def collect_metadata(self) -> Database:
        if not self._root.is_dir():
            raise SourceReaderError(f"CSV folder not found: {self._root}")

        self._logger.info(f"scanning CSV folder: {self._root}")
        database = Database(self._root.name or "csv")
        database.add_schema(Schema(self._schema))

        for path in sorted(self._root.glob("*.csv")):
            table = Table(path.stem)
            for index, header in enumerate(self._read_header(path)):
                column = Column(name=header, type="text", nullable=True)
                if index == 0:
                    column.constraint = "PRIMARY KEY"
                    column.nullable = False
                table.add_column(column)
            database.add_table(self._schema, table)
            self._logger.debug(f"discovered table {table.name} with {len(table.columns)} columns")

        return database

    def iter_rows(
        self, schema: str, table: Table, limit: int = -1
    ) -> Iterator[Tuple[Any, ...]]:
        path = self._root / f"{table.name}.csv"
        if not path.is_file():
            return
        with path.open("r", encoding="utf-8", newline="") as stream:
            reader = csv.reader(stream, delimiter=self._delimiter)
            next(reader, None)
            for index, row in enumerate(reader):
                if 0 <= limit <= index:
                    return
                yield tuple(value if value != "" else None for value in row)

    def _read_header(self, path: Path) -> list[str]:
        with path.open("r", encoding="utf-8", newline="") as stream:
            reader = csv.reader(stream, delimiter=self._delimiter)
            header = next(reader, None)
        if not header:
            raise SourceReaderError(f"CSV file is empty: {path}")
        return [name.strip() for name in header]


def build_reader(config: AppConfig, logger: Logger) -> CsvFolderReader:
    """Entry-point factory."""
    return CsvFolderReader(config, logger)
