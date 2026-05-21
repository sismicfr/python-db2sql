"""Plugin registry: resolve reader/emitter/writer factories from entry-points.

Three entry-point groups are supported:

* ``db2sql.readers`` — factories returning a :class:`SourceReader`
* ``db2sql.emitters`` — factories returning a :class:`SqlEmitter`
* ``db2sql.writers`` — factories returning a :class:`TargetWriter`

A manual in-process registry exists for tests/plugins that cannot rely on
distribution metadata.
"""

from __future__ import annotations

from importlib import metadata
from typing import Any, Callable, cast, Dict, List

from db2sql.application.ports import Logger, SourceReader, SqlEmitter, TargetWriter
from db2sql.infrastructure.config import AppConfig

READERS_GROUP = "db2sql.readers"
EMITTERS_GROUP = "db2sql.emitters"
WRITERS_GROUP = "db2sql.writers"

ReaderFactory = Callable[[AppConfig, Logger], SourceReader]
EmitterFactory = Callable[..., SqlEmitter]
WriterFactory = Callable[[AppConfig, Logger], TargetWriter]


class UnknownReaderError(Exception):
    def __init__(self, name: str, known: List[str]) -> None:
        super().__init__(
            f"Unknown reader {name!r}; known readers: {', '.join(sorted(known)) or 'none'}"
        )
        self.name = name


class UnknownEmitterError(Exception):
    def __init__(self, name: str, known: List[str]) -> None:
        super().__init__(
            f"Unknown emitter {name!r}; known emitters: {', '.join(sorted(known)) or 'none'}"
        )
        self.name = name


class UnknownWriterError(Exception):
    def __init__(self, name: str, known: List[str]) -> None:
        super().__init__(
            f"Unknown writer {name!r}; known writers: {', '.join(sorted(known)) or 'none'}"
        )
        self.name = name


_manual_readers: Dict[str, ReaderFactory] = {}
_manual_emitters: Dict[str, EmitterFactory] = {}
_manual_writers: Dict[str, WriterFactory] = {}


def register_reader(name: str, factory: ReaderFactory) -> None:
    _manual_readers[name] = factory


def register_emitter(name: str, factory: EmitterFactory) -> None:
    _manual_emitters[name] = factory


def register_writer(name: str, factory: WriterFactory) -> None:
    _manual_writers[name] = factory


def _load_entry_points(group: str) -> Dict[str, Any]:
    loaded: Dict[str, Any] = {}
    try:
        eps = metadata.entry_points(group=group)
    except TypeError:
        legacy = metadata.entry_points()
        eps = legacy.get(group, [])  # type: ignore[attr-defined]
    for entry in eps:
        loaded[entry.name] = entry.load()
    return loaded


def available_readers() -> List[str]:
    return sorted({*_load_entry_points(READERS_GROUP).keys(), *_manual_readers.keys()})


def available_emitters() -> List[str]:
    return sorted({*_load_entry_points(EMITTERS_GROUP).keys(), *_manual_emitters.keys()})


def available_writers() -> List[str]:
    return sorted({*_load_entry_points(WRITERS_GROUP).keys(), *_manual_writers.keys()})


def get_source_reader(name: str, config: AppConfig, logger: Logger) -> SourceReader:
    if name in _manual_readers:
        return _manual_readers[name](config, logger)
    eps = _load_entry_points(READERS_GROUP)
    if name in eps:
        return cast(SourceReader, eps[name](config, logger))
    raise UnknownReaderError(name, available_readers())


def get_sql_emitter(name: str, **kwargs: Any) -> SqlEmitter:
    if name in _manual_emitters:
        return _manual_emitters[name](**kwargs)
    eps = _load_entry_points(EMITTERS_GROUP)
    if name in eps:
        return cast(SqlEmitter, eps[name](**kwargs))
    raise UnknownEmitterError(name, available_emitters())


def get_target_writer(name: str, config: AppConfig, logger: Logger) -> TargetWriter:
    if name in _manual_writers:
        return _manual_writers[name](config, logger)
    eps = _load_entry_points(WRITERS_GROUP)
    if name in eps:
        return cast(TargetWriter, eps[name](config, logger))
    raise UnknownWriterError(name, available_writers())
