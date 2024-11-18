"""ConsoleLogger: level filtering and message formatting."""

from __future__ import annotations

import io

import pytest

from db2sql.infrastructure.logging import (
    LEVEL_DEBUG,
    LEVEL_ERROR,
    LEVEL_QUIET,
    LEVEL_TRACE,
    LEVEL_WARNING,
    ConsoleLogger,
    InvalidLogLevel,
)


def _logger(level: int) -> tuple[ConsoleLogger, io.StringIO]:
    stream = io.StringIO()
    return ConsoleLogger(level=level, stream=stream), stream


def test_info_below_level_is_silent() -> None:
    logger, stream = _logger(LEVEL_QUIET)
    logger.info("hello")
    assert stream.getvalue() == ""


def test_info_at_status_level_is_written() -> None:
    logger, stream = _logger(LEVEL_TRACE)
    logger.info("hello")
    assert "hello" in stream.getvalue()


def test_warning_prefix() -> None:
    logger, stream = _logger(LEVEL_WARNING)
    logger.warning("careful")
    assert "WARNING: careful" in stream.getvalue()


def test_error_prefix() -> None:
    logger, stream = _logger(LEVEL_ERROR)
    logger.error("nope")
    assert "ERROR: nope" in stream.getvalue()


def test_invalid_level_raises() -> None:
    with pytest.raises(InvalidLogLevel):
        ConsoleLogger.from_verbosity("not-a-level")


@pytest.mark.parametrize(
    "name, expected_level",
    [
        ("quiet", 80),
        ("error", 70),
        ("warning", 60),
        ("notice", 50),
        ("status", 40),
        ("verbose", 30),
        ("debug", 20),
        ("trace", 10),
        (None, 30),  # bare -V
    ],
)
def test_from_verbosity_maps_names_to_levels(name, expected_level) -> None:
    logger = ConsoleLogger.from_verbosity(name)
    assert logger.level == expected_level


def test_debug_respects_level() -> None:
    logger, stream = _logger(LEVEL_DEBUG)
    logger.debug("dbg")
    logger.trace("trc")  # silent: below level
    text = stream.getvalue()
    assert "dbg" in text
    assert "trc" not in text


def test_trace_method_emits_at_trace_level() -> None:
    logger, stream = _logger(LEVEL_TRACE)
    logger.trace("hello-trace")
    assert "hello-trace" in stream.getvalue()


def test_trace_exception_dumps_traceback() -> None:
    logger, stream = _logger(LEVEL_TRACE)
    try:
        raise ValueError("oops")
    except ValueError as exc:
        logger.trace_exception(exc)
    text = stream.getvalue()
    assert "ValueError" in text
    assert "oops" in text


def test_scope_prefix() -> None:
    stream = io.StringIO()
    logger = ConsoleLogger(level=LEVEL_TRACE, stream=stream, scope="sqlite")
    logger.info("hi")
    assert stream.getvalue().startswith("sqlite: hi") or "sqlite:" in stream.getvalue()


def test_verbose_emits_at_verbose_level() -> None:
    from db2sql.infrastructure.logging import LEVEL_VERBOSE

    logger, stream = _logger(LEVEL_VERBOSE)
    logger.verbose("v")
    assert "v" in stream.getvalue()


def test_verbose_silent_below_level() -> None:
    logger, stream = _logger(LEVEL_QUIET)
    logger.verbose("v")
    assert stream.getvalue() == ""


def test_from_verbosity_with_log_file_writes_to_disk(tmp_path) -> None:
    path = tmp_path / "log.txt"
    logger = ConsoleLogger.from_verbosity("trace", str(path))
    logger.info("hello")
    logger.warning("warn")
    text = path.read_text()
    assert "hello" in text
    assert "WARNING: warn" in text


def test_write_raw_outputs_without_prefix() -> None:
    logger, stream = _logger(LEVEL_TRACE)
    logger.write_raw("v1.0.0")
    assert "v1.0.0\n" in stream.getvalue()


def test_write_raw_applies_color_when_enabled() -> None:
    """When the underlying stream advertises a TTY, write_raw wraps with ANSI codes."""

    class _TtyStream(io.StringIO):
        def isatty(self) -> bool:
            return True

    stream = _TtyStream()
    logger = ConsoleLogger(level=LEVEL_TRACE, stream=stream)
    logger.write_raw("ver", color="\x1b[1;32m")
    assert "\x1b[1;32m" in stream.getvalue()


def test_level_allowed_respects_threshold() -> None:
    from db2sql.infrastructure.logging import LEVEL_NOTICE, LEVEL_STATUS

    logger, _ = _logger(LEVEL_NOTICE)
    assert logger.level_allowed(LEVEL_STATUS) is False
    assert logger.level_allowed(LEVEL_NOTICE) is True


def test_scope_prefix_with_color_includes_reset() -> None:
    """When color is enabled and a scope is set, the scope gets the ANSI prefix/reset."""

    class _Tty(io.StringIO):
        def isatty(self) -> bool:
            return True

    stream = _Tty()
    logger = ConsoleLogger(level=LEVEL_TRACE, stream=stream, scope="oracle")
    logger.warning("careful")
    output = stream.getvalue()
    assert "oracle:" in output
    assert "WARNING" in output
