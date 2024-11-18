"""StreamSink: writes to file when path provided, otherwise to stdout."""

from __future__ import annotations

import sys
from pathlib import Path

from db2sql.infrastructure.output import StreamSink


def test_stream_sink_writes_to_file(tmp_path: Path) -> None:
    path = tmp_path / "out.sql"
    with StreamSink(str(path)) as sink:
        sink.write("hello\n")
        sink.write("world\n")
    assert path.read_text() == "hello\nworld\n"


def test_stream_sink_writes_to_stdout_when_no_path(capsys) -> None:
    with StreamSink(None) as sink:
        sink.write("on stdout\n")
    captured = capsys.readouterr()
    assert captured.out == "on stdout\n"


def test_stream_sink_closes_owned_file_on_exit(tmp_path: Path) -> None:
    path = tmp_path / "out.sql"
    with StreamSink(str(path)) as sink:
        sink.write("x")
        stream = sink._stream  # noqa: SLF001 — test only
    assert stream.closed is True


def test_stream_sink_does_not_close_stdout(monkeypatch) -> None:
    with StreamSink(None) as _sink:
        pass
    # stdout still writable after the sink exits
    sys.stdout.write("")  # no exception
