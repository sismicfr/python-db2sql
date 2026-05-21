"""File or stdout adapter implementing the OutputSink port."""

from __future__ import annotations

import sys
from contextlib import AbstractContextManager
from types import TracebackType
from typing import IO, Optional


class StreamSink(AbstractContextManager["StreamSink"]):
    """Write to a file when ``path`` is given, otherwise to ``stdout``."""

    def __init__(self, path: Optional[str] = None) -> None:
        self._path = path
        self._owns_stream = False
        self._stream: IO[str] = sys.stdout

    def __enter__(self) -> "StreamSink":
        if self._path:
            self._stream = open(
                self._path, "w", encoding="utf-8"
            )  # noqa: SIM115 — closed in __exit__
            self._owns_stream = True
        else:
            self._stream = sys.stdout
            self._owns_stream = False
        return self

    def __exit__(
        self,
        exc_type: Optional[type[BaseException]],
        exc: Optional[BaseException],
        tb: Optional[TracebackType],
    ) -> None:
        if self._owns_stream:
            self._stream.close()

    def write(self, data: str) -> None:
        self._stream.write(data)

    def boundary(self) -> None:
        """No-op: a single stream does not rotate."""
