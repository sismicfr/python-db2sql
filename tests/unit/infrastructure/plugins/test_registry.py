"""Plugin registry: manual registration + entry-point discovery."""

from __future__ import annotations

from typing import Any, Iterator, Tuple

import pytest

from db2sql.application.ports import Logger
from db2sql.domain.model import Database, Table
from db2sql.infrastructure.config import AppConfig
from db2sql.infrastructure.plugins import (
    UnknownEmitterError,
    UnknownReaderError,
    available_emitters,
    available_readers,
    get_source_reader,
    get_sql_emitter,
    register_emitter,
    register_reader,
)


class _DummyReader:
    def __init__(self, config: AppConfig, logger: Logger) -> None:
        self.config = config
        self.logger = logger

    def collect_metadata(self) -> Database:  # pragma: no cover - not invoked
        return Database(name="x")

    def iter_rows(
        self, schema: str, table: Table, limit: int = -1
    ) -> Iterator[Tuple[Any, ...]]:  # pragma: no cover
        return iter(())


class _DummyEmitter:
    def __init__(self, **kwargs: Any) -> None:
        self.kwargs = kwargs


def test_register_and_resolve_reader() -> None:
    register_reader("dummy-reader", _DummyReader)
    try:
        instance = get_source_reader("dummy-reader", AppConfig(), logger=None)  # type: ignore[arg-type]
    finally:
        # cleanup happens implicitly via the manual registry — leave it for parallel runs
        pass
    assert isinstance(instance, _DummyReader)
    assert "dummy-reader" in available_readers()


def test_register_and_resolve_emitter() -> None:
    register_emitter("dummy-emitter", _DummyEmitter)
    emitter = get_sql_emitter("dummy-emitter", preserve_case=True)
    assert isinstance(emitter, _DummyEmitter)
    assert emitter.kwargs == {"preserve_case": True}
    assert "dummy-emitter" in available_emitters()


def test_unknown_reader_raises() -> None:
    with pytest.raises(UnknownReaderError) as exc:
        get_source_reader("no-such-reader", AppConfig(), logger=None)  # type: ignore[arg-type]
    assert "no-such-reader" in str(exc.value)


def test_unknown_emitter_raises() -> None:
    with pytest.raises(UnknownEmitterError):
        get_sql_emitter("no-such-emitter")


def test_entry_points_expose_builtin_readers() -> None:
    # the pyproject.toml exposes all four built-in readers via entry-points
    readers = available_readers()
    for name in ("sqlite", "mssql", "mysql", "postgres"):
        assert name in readers


def test_entry_points_expose_postgres_emitter() -> None:
    assert "postgres" in available_emitters()


def test_entry_points_expose_mssql_emitter() -> None:
    assert "mssql" in available_emitters()


def test_get_sql_emitter_via_entry_point_loads_postgres() -> None:
    from db2sql.infrastructure.emit.postgres import PostgresSqlEmitter

    emitter = get_sql_emitter("postgres", preserve_case=True)
    assert isinstance(emitter, PostgresSqlEmitter)


def test_get_sql_emitter_via_entry_point_loads_mssql() -> None:
    from db2sql.infrastructure.emit.mssql import MssqlSqlEmitter

    emitter = get_sql_emitter("mssql", preserve_case=True)
    assert isinstance(emitter, MssqlSqlEmitter)


def test_get_source_reader_via_entry_point_loads_sqlite() -> None:
    from db2sql.infrastructure.persistence.sqlite import SQLiteSourceReader

    class _NullLogger:
        def trace(self, m): ...
        def debug(self, m): ...
        def info(self, m): ...
        def warning(self, m): ...
        def error(self, m): ...

    reader = get_source_reader("sqlite", AppConfig(driver="sqlite"), _NullLogger())  # type: ignore[arg-type]
    assert isinstance(reader, SQLiteSourceReader)


def test_unknown_emitter_message_includes_known_names() -> None:
    with pytest.raises(UnknownEmitterError) as exc:
        get_sql_emitter("nope")
    assert "postgres" in str(exc.value)


def test_entry_point_legacy_path_is_used_when_group_kwarg_unsupported() -> None:
    """Cover the Python<3.10 fallback branch in _load_entry_points."""
    from unittest.mock import patch

    from db2sql.infrastructure.plugins import registry

    class _FakeEntry:
        def __init__(self, name: str, value: Any) -> None:
            self.name = name
            self._value = value

        def load(self) -> Any:
            return self._value

    sentinel = object()

    def _entry_points(*args: Any, **kwargs: Any):
        if "group" in kwargs:
            raise TypeError("group kwarg unsupported")
        return {registry.READERS_GROUP: [_FakeEntry("legacy", sentinel)]}

    with patch.object(registry.metadata, "entry_points", _entry_points):
        loaded = registry._load_entry_points(registry.READERS_GROUP)
    assert loaded["legacy"] is sentinel
