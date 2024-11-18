"""Shared SQLAlchemy helpers for view-export query introspection.

The ``describe_query`` and ``iter_query_rows`` operations are nearly identical
across drivers (SQLite/MSSQL/MySQL/Postgres/Oracle): execute the user-supplied
SQL, name the columns from ``Result.keys()``, and infer types either from the
DB-API ``cursor.description`` or — if we cannot trust it — from the Python type
of the first non-null value in a probe row.

We deliberately apply the ``limit`` in Python rather than rewriting the query:
user queries can include CTEs, ORDER BY, or driver-specific syntax, and any
rewrite would be fragile. Capping iteration on our side closes the cursor
early, so the database stops streaming once we stop pulling.
"""

from __future__ import annotations

import datetime
import decimal
import uuid
from typing import Any, Iterator, List, Tuple

from sqlalchemy import text
from sqlalchemy.engine import Result
from sqlalchemy.orm.session import Session

from db2sql.domain.model import Column

_DEFAULT_TYPE = "text"

_PY_TO_SQL: Tuple[Tuple[type, str], ...] = (
    (bool, "boolean"),
    (int, "integer"),
    (float, "double precision"),
    (decimal.Decimal, "numeric"),
    (str, "text"),
    (bytes, "bytea"),
    (datetime.datetime, "timestamp"),
    (datetime.date, "date"),
    (datetime.time, "time"),
    (datetime.timedelta, "interval"),
    (uuid.UUID, "uuid"),
)


def describe_query(session: Session, query: str) -> List[Column]:
    """Run ``query``, probe one row, and infer a column list from the result."""
    result: Result[Any] = session.execute(text(query))
    try:
        keys = list(result.keys())
        probe = result.fetchone()
    finally:
        result.close()
    columns: List[Column] = []
    for index, name in enumerate(keys):
        value = probe[index] if probe is not None else None
        columns.append(
            Column(
                name=str(name),
                type=_infer_type(value),
                nullable=value is None,
            )
        )
    return columns


def iter_query_rows(
    session: Session, query: str, limit: int = -1
) -> Iterator[Tuple[Any, ...]]:
    """Execute ``query`` and yield rows, stopping after ``limit`` if positive."""
    result: Result[Any] = session.execute(text(query))
    try:
        for index, row in enumerate(result):
            if limit and limit > 0 and index >= limit:
                break
            yield tuple(row)
    finally:
        result.close()


def _infer_type(value: Any) -> str:
    if value is None:
        return _DEFAULT_TYPE
    for py_type, sql_type in _PY_TO_SQL:
        if isinstance(value, py_type):
            return sql_type
    return _DEFAULT_TYPE
