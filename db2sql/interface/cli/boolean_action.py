"""argparse action that supports --xxx and --no-xxx."""

from __future__ import annotations

import argparse
from typing import Any, Optional, Sequence, Union


class BooleanAction(argparse.Action):
    """Handle --no-xxx --xxx command-line options."""

    def __init__(self, option_strings: Sequence[str], dest: str, **kwargs: Any) -> None:
        _option_strings = []
        for option_string in option_strings:
            _option_strings.append(option_string)
            if option_string.startswith("--"):
                _option_strings.append("--no-" + option_string[2:])

        default = kwargs.get("default")
        if (
            kwargs.get("help") is not None
            and default is not None
            and default is not argparse.SUPPRESS
        ):
            kwargs["help"] += f" (default: {default})"

        super().__init__(option_strings=_option_strings, dest=dest, nargs=0, **kwargs)

    def __call__(
        self,
        parser: argparse.ArgumentParser,
        namespace: argparse.Namespace,
        values: Optional[Union[str, Sequence[str]]] = None,
        option_string: Optional[str] = None,
    ) -> None:
        if option_string and option_string in self.option_strings:
            setattr(namespace, self.dest, not option_string.startswith("--no-"))

    def format_usage(self) -> str:
        return " | ".join(self.option_strings)
