"""Shared SQLAlchemy fakes for persistence reader unit tests.

The readers all follow the same pattern: ``_ensure_session()`` builds (lazily)
an engine + session, and ``session.execute(text(query))`` returns a result
that is either iterated row-by-row with attribute access or drained with
``fetchall()`` to get positional tuples.

We patch ``_ensure_session`` to return a :class:`FakeSession` that matches
queries by substring and returns canned results — no real SQLAlchemy
machinery is touched.
"""

from __future__ import annotations

from typing import Any, Callable, Iterable, List, Mapping, Optional, Sequence, Tuple, Union


class FakeRow(tuple):
    """A tuple that also supports attribute access (mimicking SQLAlchemy ``Row``)."""

    def __new__(cls, **fields: Any) -> "FakeRow":
        self = tuple.__new__(cls, fields.values())
        self._fields = fields  # type: ignore[attr-defined]
        return self

    def __getattr__(self, name: str) -> Any:
        fields = object.__getattribute__(self, "_fields")
        if name in fields:
            return fields[name]
        raise AttributeError(name)


class FakeResult:
    def __init__(self, rows: Sequence[Any]) -> None:
        self._rows = list(rows)

    def __iter__(self):
        return iter(self._rows)

    def fetchall(self) -> List[Any]:
        return list(self._rows)


Matcher = Union[str, Callable[[str, Optional[Mapping[str, Any]]], bool]]
Plan = List[Tuple[Matcher, Sequence[Any]]]


class FakeSession:
    """Pretends to be a SQLAlchemy session driven by a list of (matcher, rows) tuples."""

    def __init__(self, plan: Optional[Plan] = None) -> None:
        self._plan: Plan = list(plan or [])
        self.executed: List[Tuple[str, Optional[Mapping[str, Any]]]] = []

    def add(self, matcher: Matcher, rows: Sequence[Any]) -> None:
        self._plan.append((matcher, rows))

    def execute(self, statement: Any, params: Optional[Mapping[str, Any]] = None) -> FakeResult:
        query = str(statement)
        self.executed.append((query, params))
        for matcher, rows in self._plan:
            if isinstance(matcher, str):
                if matcher in query:
                    return FakeResult(rows)
            elif matcher(query, params):
                return FakeResult(rows)
        return FakeResult([])


def install_fake_session(reader: Any, session: FakeSession) -> FakeSession:
    """Replace the reader's ``_ensure_session`` with one that returns *session*."""
    reader._ensure_session = lambda: session  # type: ignore[assignment]
    reader._session = session
    return session
