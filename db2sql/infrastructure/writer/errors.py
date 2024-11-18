"""Writer-layer errors."""

from __future__ import annotations


class TargetWriterError(Exception):
    """Generic failure while writing into a target database."""

    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message


class TargetWriterConnectionError(TargetWriterError):
    """Cannot establish a connection to the target database."""


class TargetWriterExecutionError(TargetWriterError):
    """A DDL/DML statement failed on the target database."""
