"""Port for the destination of the generated SQL stream."""

from __future__ import annotations

from typing import Protocol


class OutputSink(Protocol):
    """A line-oriented text sink. Implementations can wrap stdout, files, buffers..."""

    def write(self, data: str) -> None: ...

    def boundary(self) -> None:
        """Signal that a safe split point has been reached.

        Emitters call this after a complete top-level statement (e.g. after the
        trailing ``;`` or after ``\\.`` in a Postgres COPY block). Sinks that do
        not rotate output (stdout, single file, live executor) can ignore it.
        """
