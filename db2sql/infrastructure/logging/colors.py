"""ANSI color helpers used by the console logger."""

from __future__ import annotations

import os
from typing import Any

import colorama
from colorama import Fore, Style

from db2sql import const


def is_terminal(stream: Any) -> bool:
    return hasattr(stream, "isatty") and stream.isatty()


def color_enabled(stream: object) -> bool:
    """Follow https://bixense.com/clicolors conventions, falling back to TTY detection."""
    if os.getenv(const.ENV_NO_COLOR, "0") != "0":
        return True
    if os.getenv(const.ENV_CLICOLOR_FORCE) is not None:
        return True
    return is_terminal(stream)


def init_colorama(stream: object) -> None:
    if color_enabled(stream):
        if os.getenv(const.ENV_CLICOLOR_FORCE, "0") != "0":
            colorama.init(strip=False, convert=False)
        else:
            colorama.init()


class Palette:  # pylint: disable=too-few-public-methods
    """Wrapper around colorama colors."""

    RED = Fore.RED
    WHITE = Fore.WHITE
    CYAN = Fore.CYAN
    GREEN = Fore.GREEN
    MAGENTA = Fore.MAGENTA
    BLUE = Fore.BLUE
    YELLOW = Fore.YELLOW
    BLACK = Fore.BLACK

    BRIGHT_RED = Style.BRIGHT + Fore.RED
    BRIGHT_BLUE = Style.BRIGHT + Fore.BLUE
    BRIGHT_YELLOW = Style.BRIGHT + Fore.YELLOW
    BRIGHT_GREEN = Style.BRIGHT + Fore.GREEN
    BRIGHT_CYAN = Style.BRIGHT + Fore.CYAN
    BRIGHT_WHITE = Style.BRIGHT + Fore.WHITE
    BRIGHT_MAGENTA = Style.BRIGHT + Fore.MAGENTA


if os.getenv(const.ENV_DB2SQL_COLOR_DARK):
    Palette.WHITE = Fore.BLACK
    Palette.CYAN = Fore.BLUE
    Palette.YELLOW = Fore.MAGENTA
    Palette.BRIGHT_WHITE = Fore.BLACK
    Palette.BRIGHT_CYAN = Fore.BLUE
    Palette.BRIGHT_YELLOW = Fore.MAGENTA
    Palette.BRIGHT_GREEN = Fore.GREEN


RESET = Style.RESET_ALL
