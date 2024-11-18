"""Smoke test for ``python -m db2sql``."""

from __future__ import annotations

import runpy
import subprocess
import sys

import pytest


def test_main_module_invokes_cli(monkeypatch: pytest.MonkeyPatch) -> None:
    """Importing ``db2sql.__main__`` and exposing its ``main`` is what the entry-point relies on."""
    monkeypatch.delenv("DB2SQL_CONFIG", raising=False)
    monkeypatch.setattr(sys, "argv", ["db2sql", "--driver", "no-such-driver"])
    with pytest.raises(SystemExit) as exc:
        runpy.run_module("db2sql", run_name="__main__")
    # Unknown driver is converted to invalid-configuration in main()
    assert exc.value.code == 5


def test_python_minus_m_db2sql_prints_help() -> None:
    """``python -m db2sql --help`` produces the usage text on stdout."""
    result = subprocess.run(
        [sys.executable, "-m", "db2sql", "--help"],
        capture_output=True,
        text=True,
        env={"PATH": "/usr/bin:/usr/local/bin", "DB2SQL_CONFIG": ""},
    )
    assert "usage: db2sql" in result.stdout
