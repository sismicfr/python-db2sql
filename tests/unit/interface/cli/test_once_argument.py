"""OnceArgument: each option can be specified at most once."""

from __future__ import annotations

import argparse

import pytest

from db2sql.interface.cli.once_argument import OnceArgument


def _parser(default: object = None) -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(exit_on_error=False)
    parser.add_argument("--driver", dest="driver", action=OnceArgument, default=default)
    return parser


def test_first_use_sets_value() -> None:
    ns = _parser().parse_args(["--driver", "sqlite"])
    assert ns.driver == "sqlite"


def test_second_use_raises_argument_error() -> None:
    parser = _parser()
    with pytest.raises((argparse.ArgumentError, SystemExit)):
        parser.parse_args(["--driver", "sqlite", "--driver", "postgres"])


def test_default_value_is_treated_as_unset_and_overridden() -> None:
    """If ``default`` is given, the action still allows a single override."""
    parser = _parser(default="mssql")
    ns = parser.parse_args(["--driver", "sqlite"])
    assert ns.driver == "sqlite"


def test_when_default_is_set_double_use_does_not_raise() -> None:
    """With an explicit non-None default, the once-check is bypassed."""
    parser = _parser(default="mssql")
    ns = parser.parse_args(["--driver", "sqlite", "--driver", "postgres"])
    assert ns.driver == "postgres"
