"""PostgreSQL TargetWriter adapter."""

from db2sql.application.ports import Logger
from db2sql.infrastructure.config import AppConfig

from .writer import PostgresTargetWriter


def build_writer(config: AppConfig, logger: Logger) -> PostgresTargetWriter:
    """Plugin entry-point factory."""
    return PostgresTargetWriter(config, logger)


__all__ = ["PostgresTargetWriter", "build_writer"]
