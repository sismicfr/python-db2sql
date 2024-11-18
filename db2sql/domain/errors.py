"""Domain-level errors. No infrastructure dependencies."""

from __future__ import annotations


class DomainError(Exception):
    """Base class for all domain-level errors."""

    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message


class DuplicatedItemError(DomainError):
    """Generic duplicated-item error."""


class DuplicatedSchemaError(DuplicatedItemError):
    def __init__(self, name: str) -> None:
        super().__init__(f"{name} schema already collected")


class DuplicatedTableError(DuplicatedItemError):
    def __init__(self, name: str) -> None:
        super().__init__(f"{name} table already collected")


class DuplicatedColumnError(DuplicatedItemError):
    def __init__(self, name: str) -> None:
        super().__init__(f"{name} column already collected")
