"""Logging adapter — ConsoleLogger implements the application Logger port."""

from .colors import Palette, color_enabled, init_colorama, is_terminal
from .console_logger import (
    LEVEL_DEBUG,
    LEVEL_ERROR,
    LEVEL_NOTICE,
    LEVEL_QUIET,
    LEVEL_STATUS,
    LEVEL_TRACE,
    LEVEL_VERBOSE,
    LEVEL_WARNING,
    ConsoleLogger,
    InvalidLogLevel,
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
