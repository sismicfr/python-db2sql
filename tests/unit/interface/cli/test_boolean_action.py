"""BooleanAction: --xxx / --no-xxx parsing and help-string handling."""

from __future__ import annotations

import argparse

import pytest

from db2sql.interface.cli.boolean_action import BooleanAction


def _parser(**kwargs: object) -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    parser.add_argument("--feature", dest="feature", action=BooleanAction, **kwargs)
    return parser


def test_positive_flag_sets_true() -> None:
    ns = _parser().parse_args(["--feature"])
    assert ns.feature is True


def test_negative_flag_sets_false() -> None:
    ns = _parser().parse_args(["--no-feature"])
    assert ns.feature is False


def test_default_is_used_when_flag_absent() -> None:
    ns = _parser(default=True).parse_args([])
    assert ns.feature is True


def test_help_string_is_augmented_with_default() -> None:
    parser = _parser(default=True, help="enable thing")
    action = parser._actions[-1]
    assert "(default: True)" in (action.help or "")


def test_short_option_without_double_dash_is_kept_as_is() -> None:
    """Only ``--`` options get a ``--no-`` mirror."""
    parser = argparse.ArgumentParser()
    parser.add_argument("-f", dest="flag", action=BooleanAction)
    ns = parser.parse_args(["-f"])
    # Short flag still toggles the value: it does not match the ``--no-`` prefix,
    # so the value becomes True.
    assert ns.flag is True


def test_format_usage_joins_option_strings() -> None:
    parser = _parser()
    action = parser._actions[-1]
    usage = action.format_usage()
    assert "--feature" in usage and "--no-feature" in usage
