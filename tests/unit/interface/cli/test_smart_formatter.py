"""SmartFormatter preserves indentation in description text."""

from __future__ import annotations

import argparse

from db2sql.interface.cli.smart_formatter import SmartFormatter


def test_smart_formatter_preserves_indented_lines() -> None:
    description = (
        "Header line\n"
        "    indented line one\n"
        "    indented line two\n"
    )
    parser = argparse.ArgumentParser(
        prog="db2sql", description=description, formatter_class=SmartFormatter
    )
    help_text = parser.format_help()
    # Both indented lines remain intact, not re-flowed
    assert "indented line one" in help_text
    assert "indented line two" in help_text
