"""Port for application logging (decoupled from any concrete logger)."""

from __future__ import annotations

from typing import Protocol


class Logger(Protocol):
    """Minimal logger interface used by the use case and adapters."""

    def trace(self, message: str) -> None: ...

    def debug(self, message: str) -> None: ...

    def info(self, message: str) -> None: ...

    def warning(self, message: str) -> None: ...

    def error(self, message: str) -> None: ...
