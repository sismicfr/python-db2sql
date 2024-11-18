"""MySQL SourceReader adapter."""

from db2sql.application.ports import Logger
from db2sql.infrastructure.config import AppConfig

from .reader import MySQLSourceReader


def build_reader(config: AppConfig, logger: Logger) -> MySQLSourceReader:
    """Plugin entry-point factory."""
    return MySQLSourceReader(config, logger)


__all__ = ["MySQLSourceReader", "build_reader"]
