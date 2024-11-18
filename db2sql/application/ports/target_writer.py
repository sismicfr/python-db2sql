"""Port for writing directly into a target database (live migration)."""

from __future__ import annotations

from typing import Any, Iterator, Protocol, Tuple

from db2sql.domain.model import Table


class TargetWriter(Protocol):
    """Execute DDL and bulk-load rows into a target database.

    Implementations are infrastructure adapters (psycopg2, pymssql, …). The
    application layer never sees a concrete driver: it only manipulates the
    port and lets the writer translate domain operations into driver calls.

    Implementations are context managers: ``__enter__`` opens the connection
    and runs ``session_setup`` statements; ``__exit__`` commits (or rolls back
    on exception) and closes the connection.
    """

    def __enter__(self) -> "TargetWriter": ...

    def __exit__(self, exc_type: Any, exc: Any, tb: Any) -> None: ...

    def execute_ddl(self, statement: str) -> None:
        """Execute a single DDL/DML statement produced by the SqlEmitter."""

    def bulk_load(
        self,
        schema: str,
        table: Table,
        rows: Iterator[Tuple[Any, ...]],
    ) -> None:
        """Bulk-insert ``rows`` into ``schema.table`` using the fastest native path."""
