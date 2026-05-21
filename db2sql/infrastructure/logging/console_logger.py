"""Console implementation of the application :class:`Logger` port."""

from __future__ import annotations

import sys
import traceback
from typing import IO, Optional

from .colors import color_enabled, Palette, RESET

LEVEL_QUIET = 80
LEVEL_ERROR = 70
LEVEL_WARNING = 60
LEVEL_NOTICE = 50
LEVEL_STATUS = 40
LEVEL_VERBOSE = 30
LEVEL_DEBUG = 20
LEVEL_TRACE = 10


_LEVEL_NAMES = {
    "quiet": LEVEL_QUIET,
    "error": LEVEL_ERROR,
    "warning": LEVEL_WARNING,
    "notice": LEVEL_NOTICE,
    "status": LEVEL_STATUS,
    "info": LEVEL_STATUS,
    None: LEVEL_VERBOSE,
    "verbose": LEVEL_VERBOSE,
    "debug": LEVEL_DEBUG,
    "V": LEVEL_DEBUG,
    "trace": LEVEL_TRACE,
    "VV": LEVEL_TRACE,
}


class InvalidLogLevel(Exception):
    def __init__(self, name: Optional[str]) -> None:
        super().__init__(f"Invalid argument '-V{name}'")
        self.message = f"Invalid argument '-V{name}'"


class ConsoleLogger:
    """An ANSI-aware logger that writes to a stream. Implements the ``Logger`` port."""

    def __init__(
        self,
        level: int = LEVEL_STATUS,
        stream: Optional[IO[str]] = None,
        scope: str = "",
    ) -> None:
        self._level = level
        self._stream: IO[str] = stream if stream is not None else sys.stdout
        self._scope = scope
        self._color = color_enabled(self._stream)

    @classmethod
    def from_verbosity(
        cls,
        level_name: Optional[str] = None,
        log_file: Optional[str] = None,
    ) -> "ConsoleLogger":
        try:
            level = _LEVEL_NAMES[level_name]
        except KeyError as exc:
            raise InvalidLogLevel(level_name) from exc
        stream: IO[str]
        if log_file:
            stream = open(
                log_file, "wt", encoding="utf-8"
            )  # noqa: SIM115 — owned for process lifetime
        else:
            stream = sys.stdout
        return cls(level=level, stream=stream)

    @property
    def level(self) -> int:
        return self._level

    def level_allowed(self, level: int) -> bool:
        return self._level <= level

    def _emit(self, message: str, color: Optional[str] = None) -> None:
        prefix = ""
        if self._scope:
            if self._color:
                prefix = f"{color or ''}{self._scope}:{RESET} "
            else:
                prefix = f"{self._scope}: "
        body = f"{color}{message}{RESET}" if (color and self._color) else message
        self._stream.write(f"{prefix}{body}\n")
        self._stream.flush()

    def trace(self, message: str) -> None:
        if self._level <= LEVEL_TRACE:
            self._emit(message, color=Palette.BRIGHT_WHITE)

    def debug(self, message: str) -> None:
        if self._level <= LEVEL_DEBUG:
            self._emit(message)

    def verbose(self, message: str) -> None:
        if self._level <= LEVEL_VERBOSE:
            self._emit(message)

    def info(self, message: str) -> None:
        if self._level <= LEVEL_STATUS:
            self._emit(message)

    def warning(self, message: str) -> None:
        if self._level <= LEVEL_WARNING:
            self._emit(f"WARNING: {message}", color=Palette.YELLOW)

    def error(self, message: str) -> None:
        if self._level <= LEVEL_ERROR:
            self._emit(f"ERROR: {message}", color=Palette.RED)

    def trace_exception(self, exc: BaseException) -> None:
        if self._level <= LEVEL_TRACE:
            text = "\n".join(traceback.format_exception(type(exc), exc, exc.__traceback__))
            self._emit(text, color=Palette.BRIGHT_WHITE)

    def write_raw(self, text: str, color: Optional[str] = None) -> None:
        """Direct write, bypassing scope/level (used for ``--version``-like output)."""
        if color and self._color:
            self._stream.write(f"{color}{text}{RESET}\n")
        else:
            self._stream.write(f"{text}\n")
        self._stream.flush()
