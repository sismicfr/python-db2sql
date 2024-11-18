"""OutputSink that executes each SQL statement against a :class:`TargetWriter`.

The sink keeps the :class:`SqlEmitter` API untouched: the emitter still calls
``sink.write(str)`` exactly like it does for a file dump. The only difference
is that the chunks are buffered and split on statement boundaries, then handed
to the writer for execution.

This is what guarantees the DDL-identity invariant: the SQL strings produced
by the emitter are executed verbatim — there is no second code path that
re-renders the DDL.
"""

from __future__ import annotations

from contextlib import AbstractContextManager
from types import TracebackType
from typing import List, Optional

from db2sql.application.ports import TargetWriter


class ExecutingSink(AbstractContextManager["ExecutingSink"]):
    """Pipe SqlEmitter output into ``writer.execute_ddl`` one statement at a time.

    Statements are split on the ``;`` followed by a newline pattern produced by
    both emitters. A trailing ``\\n`` inside an unterminated chunk is kept in
    the buffer until the next ``write`` (or ``close``) call completes the
    statement. Empty statements are ignored.
    """

    def __init__(self, writer: TargetWriter) -> None:
        self._writer = writer
        self._buffer: List[str] = []

    def __enter__(self) -> "ExecutingSink":
        return self

    def __exit__(
        self,
        exc_type: Optional[type[BaseException]],
        exc: Optional[BaseException],
        tb: Optional[TracebackType],
    ) -> None:
        self.flush()

    def write(self, data: str) -> None:
        if not data:
            return
        self._buffer.append(data)
        joined = "".join(self._buffer)
        if ";" not in joined:
            return
        statements, remainder = self._split_statements(joined)
        self._buffer = [remainder] if remainder else []
        for stmt in statements:
            stripped = stmt.strip()
            if stripped and stripped.rstrip(";").strip():
                self._writer.execute_ddl(stripped)

    def boundary(self) -> None:
        """No-op: the executor processes complete statements as it sees them."""

    def flush(self) -> None:
        """Execute any remaining buffered content (no trailing ``;`` allowed)."""
        if not self._buffer:
            return
        remaining = "".join(self._buffer).strip()
        self._buffer = []
        if remaining:
            self._writer.execute_ddl(remaining)

    @staticmethod
    def _split_statements(text: str) -> tuple[List[str], str]:
        """Split ``text`` on ``;`` boundaries, returning complete stmts + remainder.

        Naive splitting on ``;`` is enough here because the emitters never put
        literal ``;`` inside identifiers or string literals at DDL time. Data
        rows go through ``bulk_load`` and never reach this sink.
        """
        parts = text.split(";")
        remainder = parts.pop()
        return [p + ";" for p in parts], remainder
