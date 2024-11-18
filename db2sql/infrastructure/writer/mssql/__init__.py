"""Microsoft SQL Server TargetWriter adapter."""

from db2sql.application.ports import Logger
from db2sql.infrastructure.config import AppConfig

from .writer import MssqlTargetWriter


def build_writer(config: AppConfig, logger: Logger) -> MssqlTargetWriter:
    """Plugin entry-point factory."""
    return MssqlTargetWriter(config, logger)


__all__ = ["MssqlTargetWriter", "build_writer"]
