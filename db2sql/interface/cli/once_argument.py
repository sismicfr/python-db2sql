"""argparse action that allows only one occurrence of an argument."""

from __future__ import annotations

import argparse
from typing import Any, Optional, Sequence, Union


class OnceArgument(argparse.Action):
    """Allows declaring a parameter that can have only one value."""

    def __call__(
        self,
        parser: argparse.ArgumentParser,
        namespace: argparse.Namespace,
        values: Union[str, Any, Sequence[Any], None],
        option_string: Optional[str] = None,
    ) -> None:
        # A SUPPRESS default means argparse leaves the attribute unset until the
        # flag is seen, so a present value can only come from a first occurrence
        # — same situation as a None default, and the check applies as well.
        unset_by_default = self.default is None or self.default is argparse.SUPPRESS
        if getattr(namespace, self.dest, None) is not None and unset_by_default:
            msg = f"{option_string or 'undefined'} can only be specified once"
            raise argparse.ArgumentError(None, msg)
        setattr(namespace, self.dest, values)
