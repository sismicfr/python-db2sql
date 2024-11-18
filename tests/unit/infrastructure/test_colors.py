"""ANSI color helpers: TTY detection, env-var overrides, dark palette."""

from __future__ import annotations

import importlib
from unittest.mock import patch

import pytest

from db2sql.infrastructure.logging import colors


class _FakeStream:
    def __init__(self, tty: bool) -> None:
        self._tty = tty

    def isatty(self) -> bool:
        return self._tty


def test_is_terminal_returns_true_for_tty() -> None:
    assert colors.is_terminal(_FakeStream(True)) is True


def test_is_terminal_returns_false_for_pipe() -> None:
    assert colors.is_terminal(_FakeStream(False)) is False


def test_is_terminal_handles_streams_without_isatty() -> None:
    assert colors.is_terminal(object()) is False


def test_color_enabled_respects_no_color(monkeypatch) -> None:
    monkeypatch.setenv("NO_COLOR", "1")
    monkeypatch.delenv("CLICOLOR_FORCE", raising=False)
    assert colors.color_enabled(_FakeStream(False)) is True


def test_color_enabled_respects_clicolor_force(monkeypatch) -> None:
    monkeypatch.setenv("NO_COLOR", "0")
    monkeypatch.setenv("CLICOLOR_FORCE", "1")
    assert colors.color_enabled(_FakeStream(False)) is True


def test_color_enabled_falls_back_to_isatty(monkeypatch) -> None:
    monkeypatch.setenv("NO_COLOR", "0")
    monkeypatch.delenv("CLICOLOR_FORCE", raising=False)
    assert colors.color_enabled(_FakeStream(True)) is True
    assert colors.color_enabled(_FakeStream(False)) is False


def test_init_colorama_calls_init_when_color_enabled(monkeypatch) -> None:
    monkeypatch.setenv("NO_COLOR", "0")
    monkeypatch.delenv("CLICOLOR_FORCE", raising=False)
    with patch("db2sql.infrastructure.logging.colors.colorama.init") as init:
        colors.init_colorama(_FakeStream(True))
    init.assert_called_once_with()


def test_init_colorama_uses_strip_false_with_force(monkeypatch) -> None:
    monkeypatch.setenv("CLICOLOR_FORCE", "1")
    with patch("db2sql.infrastructure.logging.colors.colorama.init") as init:
        colors.init_colorama(_FakeStream(False))
    init.assert_called_once_with(strip=False, convert=False)


def test_init_colorama_noop_when_color_disabled(monkeypatch) -> None:
    monkeypatch.setenv("NO_COLOR", "0")
    monkeypatch.delenv("CLICOLOR_FORCE", raising=False)
    with patch("db2sql.infrastructure.logging.colors.colorama.init") as init:
        colors.init_colorama(_FakeStream(False))
    init.assert_not_called()


def test_dark_palette_remaps_colors_on_import(monkeypatch) -> None:
    """Reloading the module with DB2SQL_COLOR_DARK swaps a few Palette entries."""
    monkeypatch.setenv("DB2SQL_COLOR_DARK", "1")
    try:
        dark = importlib.reload(colors)
        from colorama import Fore

        assert dark.Palette.WHITE == Fore.BLACK
        assert dark.Palette.CYAN == Fore.BLUE
        assert dark.Palette.YELLOW == Fore.MAGENTA
    finally:
        monkeypatch.delenv("DB2SQL_COLOR_DARK", raising=False)
        importlib.reload(colors)
