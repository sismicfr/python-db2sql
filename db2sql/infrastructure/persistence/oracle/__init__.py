"""Oracle SourceReader adapter."""

from db2sql.application.ports import Logger
from db2sql.infrastructure.config import AppConfig

from .reader import OracleSourceReader


def build_reader(config: AppConfig, logger: Logger) -> OracleSourceReader:
    """Plugin entry-point factory."""
    return OracleSourceReader(config, logger)


__all__ = ["OracleSourceReader", "build_reader"]
