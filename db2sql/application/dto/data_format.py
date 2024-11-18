"""DataFormat enum — application-level, no pydantic dependency."""

from __future__ import annotations

from enum import Enum


class DataFormat(str, Enum):
    """How table data should be emitted in the SQL dump."""

    COPY = "copy"
    INSERT = "insert"
