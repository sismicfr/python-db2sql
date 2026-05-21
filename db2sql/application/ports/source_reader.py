"""Port for reading a source database."""

from __future__ import annotations

from typing import Any, Iterator, List, Protocol, Tuple

from db2sql.domain.model import Column, Database, Table


class SourceReader(Protocol):
    """Reads schema metadata and rows from a source database."""

    def collect_metadata(self) -> Database:
        """Return the populated :class:`Database` aggregate."""

    def iter_rows(self, schema: str, table: Table, limit: int = -1) -> Iterator[Tuple[Any, ...]]:
        """Yield rows from ``schema.table`` as tuples. ``limit`` of ``-1`` means no limit."""

    def describe_query(self, query: str) -> List[Column]:
        """Infer the columns produced by ``query``.

        Implementations typically run the query (or a probe variant) and infer
        each column's type from the result-set metadata or from a sample row.
        """

    def iter_query_rows(self, query: str, limit: int = -1) -> Iterator[Tuple[Any, ...]]:
        """Execute ``query`` and yield rows as tuples. ``limit`` of ``-1`` means no limit."""
