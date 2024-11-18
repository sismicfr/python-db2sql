"""argparse help formatter that preserves indentation."""

from __future__ import annotations

import argparse
import textwrap


class SmartFormatter(argparse.HelpFormatter):
    """Text formatter for db2sql commands."""

    def _fill_text(self, text: str, width: int, indent: str) -> str:
        text = textwrap.dedent(text)
        return "".join(indent + line for line in text.splitlines(True))
