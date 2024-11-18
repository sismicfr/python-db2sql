"""Output adapters implementing the OutputSink port."""

from .executing_sink import ExecutingSink
from .rotating_file_sink import RotatingFileSink
from .stream_sink import StreamSink

__all__ = ["ExecutingSink", "RotatingFileSink", "StreamSink"]
