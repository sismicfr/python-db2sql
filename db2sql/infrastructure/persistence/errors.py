"""Persistence-layer errors."""

from __future__ import annotations


class SourceReaderError(Exception):
    """Failed to collect information from the source database."""

    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message
