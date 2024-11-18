"""SQLite SourceReader adapter."""

from db2sql.application.ports import Logger
from db2sql.infrastructure.config import AppConfig

from .reader import SQLiteSourceReader


def build_reader(config: AppConfig, logger: Logger) -> SQLiteSourceReader:
    """Plugin entry-point factory."""
    return SQLiteSourceReader(config, logger)


__all__ = ["SQLiteSourceReader", "build_reader"]
