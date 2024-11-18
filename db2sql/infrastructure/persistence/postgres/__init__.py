"""PostgreSQL SourceReader adapter."""

from db2sql.application.ports import Logger
from db2sql.infrastructure.config import AppConfig

from .reader import PostgresSourceReader


def build_reader(config: AppConfig, logger: Logger) -> PostgresSourceReader:
    """Plugin entry-point factory."""
    return PostgresSourceReader(config, logger)


__all__ = ["PostgresSourceReader", "build_reader"]
