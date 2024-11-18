"""MSSQL SourceReader adapter."""

from db2sql.application.ports import Logger
from db2sql.infrastructure.config import AppConfig

from .reader import MSSQLSourceReader


def build_reader(config: AppConfig, logger: Logger) -> MSSQLSourceReader:
    """Plugin entry-point factory."""
    return MSSQLSourceReader(config, logger)


__all__ = ["MSSQLSourceReader", "build_reader"]
