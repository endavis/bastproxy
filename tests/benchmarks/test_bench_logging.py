# Project: bastproxy
# Filename: tests/benchmarks/test_bench_logging.py
#
# File Description: Performance benchmarks for the stdlib logging helpers
#
# By: Bast
"""Performance benchmarks for ``get_logger`` and ``log_to`` (#247).

The debug-off single-source call is the cost every disabled debug message pays, so it
asserts a target when benchmarks are enabled (``doit benchmark``): at most 5 us median.
A disabled run (``doit check``, CI tests) skips the assertion. The other benchmarks
are informational: ``log_to`` with two sources and debug off, debug on with only a
``NullHandler``, and debug on through the real console and file handlers.
"""

import logging
from collections.abc import Iterator
from io import StringIO
from pathlib import Path
from typing import Any

import pytest

from bastproxy.libs.logger import (
    RecordContextFilter,
    RenderFilter,
    get_logger,
    log_to,
    set_threshold,
)
from bastproxy.plugins.core.log.libs._custom_logger import (
    CustomColorFormatter,
    CustomConsoleHandler,
    CustomRotatingFileHandler,
)

CALLS = 2000
ROUNDS = 20
DEBUG_OFF_TARGET_SECONDS = 5e-6  # per call
NAME_A = "bench247.a"
NAME_B = "bench247.b"
FMT = "%(asctime)s : %(levelname)-9s - %(name)-22s - %(message)s"


@pytest.fixture
def quiet_root() -> Iterator[None]:
    """Give the root logger only a NullHandler and reset the thresholds afterwards."""
    root = logging.getLogger()
    saved = root.handlers[:]
    root.handlers = [logging.NullHandler()]
    yield
    root.handlers = saved
    for name in (NAME_A, NAME_B):
        set_threshold(name, None)


class _StubAPI:
    """No log plugin: every name is allowed, the client is not used."""

    quiet_mode = False
    startup = True

    def __call__(self, name: str) -> Any:
        return lambda *args: False


def _single(n: int) -> None:
    logger = get_logger(NAME_A)
    for i in range(n):
        logger.debug("bench message %s", i)


def _two_sources(n: int) -> None:
    for i in range(n):
        log_to([NAME_A, NAME_B], logging.DEBUG, "bench message %s", i)


@pytest.mark.benchmark
def test_bench_logger_debug_off_single_source(benchmark: Any, quiet_root: None) -> None:
    """Debug off, one source: get_logger plus a dropped debug call."""

    def run() -> None:
        for i in range(CALLS):
            get_logger(NAME_A).debug("bench message %s", i)

    benchmark.pedantic(run, rounds=ROUNDS, iterations=1)
    if not benchmark.disabled:
        per_call = benchmark.stats.stats.median / CALLS
        assert per_call <= DEBUG_OFF_TARGET_SECONDS, f"{per_call * 1e6:.2f} us per call"


@pytest.mark.benchmark
def test_bench_logger_debug_off_log_to_two_sources(benchmark: Any, quiet_root: None) -> None:
    """Debug off, two sources through log_to (informational)."""
    benchmark.pedantic(_two_sources, args=(CALLS,), rounds=ROUNDS, iterations=1)


@pytest.mark.benchmark
def test_bench_logger_debug_on_null_handler(benchmark: Any, quiet_root: None) -> None:
    """Debug on, a NullHandler only (informational)."""
    set_threshold(NAME_A, logging.DEBUG)
    set_threshold(NAME_B, logging.DEBUG)
    benchmark.pedantic(_two_sources, args=(CALLS,), rounds=ROUNDS, iterations=1)


@pytest.mark.benchmark
def test_bench_logger_debug_on_real_handlers(
    benchmark: Any, quiet_root: None, tmp_path: Path
) -> None:
    """Debug on through the console (StringIO) and file handlers (informational)."""
    set_threshold(NAME_A, logging.DEBUG)
    set_threshold(NAME_B, logging.DEBUG)
    console = CustomConsoleHandler(stream=StringIO())
    console.formatter = CustomColorFormatter(FMT)
    file_handler = CustomRotatingFileHandler(filename=tmp_path / "bench.log")
    file_handler.formatter = logging.Formatter(FMT)
    root = logging.getLogger()
    for handler in (file_handler, console):
        handler.api = _StubAPI()  # type: ignore[assignment]
        handler.addFilter(RenderFilter())
        handler.addFilter(RecordContextFilter())
        root.addHandler(handler)
    try:
        benchmark.pedantic(_two_sources, args=(CALLS,), rounds=ROUNDS, iterations=1)
    finally:
        for handler in (file_handler, console):
            root.removeHandler(handler)
        file_handler.close()
