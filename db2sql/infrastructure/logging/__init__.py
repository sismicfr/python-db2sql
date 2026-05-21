"""Logging adapter — ConsoleLogger implements the application Logger port."""

from .colors import color_enabled, init_colorama, is_terminal, Palette
from .console_logger import (
    ConsoleLogger,
    InvalidLogLevel,
    LEVEL_DEBUG,
    LEVEL_ERROR,
    LEVEL_NOTICE,
    LEVEL_QUIET,
    LEVEL_STATUS,
    LEVEL_TRACE,
    LEVEL_VERBOSE,
    LEVEL_WARNING,
)

__all__ = [
    "ConsoleLogger",
    "InvalidLogLevel",
    "LEVEL_DEBUG",
    "LEVEL_ERROR",
    "LEVEL_NOTICE",
    "LEVEL_QUIET",
    "LEVEL_STATUS",
    "LEVEL_TRACE",
    "LEVEL_VERBOSE",
    "LEVEL_WARNING",
    "Palette",
    "color_enabled",
    "init_colorama",
    "is_terminal",
]
