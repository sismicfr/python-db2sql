"""OutputSink that splits a dump into multiple files when a size limit is reached.

Rotation only happens at boundaries declared by the emitter (after a complete
statement), so a file never ends in the middle of an ``INSERT``/``COPY`` block.
The emitter calls :meth:`write` freely and :meth:`boundary` at safe split
points; this sink keeps an in-flight buffer that is flushed when either:

* a boundary is reached and the on-disk size would exceed ``max_bytes`` after
  the buffer is appended, in which case the current file is closed and a new
  one is opened before the buffer is written; or
* a boundary is reached and the buffer can be appended without crossing the
  limit, in which case it is simply written to the current file.

Output files are named by inserting a 4-digit, 1-based part index before the
suffix of ``path`` — e.g. ``dump.sql`` → ``dump-0001.sql``, ``dump-0002.sql``.
"""

from __future__ import annotations

from contextlib import AbstractContextManager
from pathlib import Path
from types import TracebackType
from typing import IO, List, Optional


class RotatingFileSink(AbstractContextManager["RotatingFileSink"]):
    """Write a dump across multiple files, rolling over at emitter boundaries."""

    def __init__(self, path: str, max_bytes: int) -> None:
        if max_bytes <= 0:
            raise ValueError("max_bytes must be > 0")
        self._template = Path(path)
        self._max_bytes = max_bytes
        self._buffer: List[str] = []
        self._part_index = 0
        self._current_path: Optional[Path] = None
        self._current_stream: Optional[IO[str]] = None
        self._current_size = 0
        self._paths: List[Path] = []

    @property
    def paths(self) -> List[Path]:
        """The list of files written so far, in rotation order."""
        return list(self._paths)

    def __enter__(self) -> "RotatingFileSink":
        self._open_next_part()
        return self

    def __exit__(
        self,
        exc_type: Optional[type[BaseException]],
        exc: Optional[BaseException],
        tb: Optional[TracebackType],
    ) -> None:
        if self._buffer:
            self._flush_buffer()
        if self._current_stream is not None:
            self._current_stream.close()
            self._current_stream = None

    def write(self, data: str) -> None:
        if not data:
            return
        self._buffer.append(data)

    def boundary(self) -> None:
        if not self._buffer:
            return
        buffered_size = sum(len(s.encode("utf-8")) for s in self._buffer)
        if self._current_size > 0 and self._current_size + buffered_size > self._max_bytes:
            self._rotate()
        self._flush_buffer()

    def _flush_buffer(self) -> None:
        assert self._current_stream is not None
        payload = "".join(self._buffer)
        self._buffer = []
        self._current_stream.write(payload)
        self._current_size += len(payload.encode("utf-8"))

    def _rotate(self) -> None:
        assert self._current_stream is not None
        self._current_stream.close()
        self._current_stream = None
        self._open_next_part()

    def _open_next_part(self) -> None:
        self._part_index += 1
        self._current_path = self._part_path(self._part_index)
        self._paths.append(self._current_path)
        parent = self._current_path.parent
        if str(parent) and not parent.exists():
            parent.mkdir(parents=True, exist_ok=True)
        self._current_stream = open(  # pylint: disable=consider-using-with
            self._current_path, "w", encoding="utf-8"
        )
        self._current_size = 0

    def _part_path(self, index: int) -> Path:
        stem = self._template.stem
        suffix = self._template.suffix
        parent = self._template.parent
        name = f"{stem}-{index:04d}{suffix}" if suffix else f"{stem}-{index:04d}"
        return parent / name if str(parent) else Path(name)
