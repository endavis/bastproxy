# Project: bastproxy
# Filename: tests/benchmarks/test_bench_processing_records.py
#
# File Description: Performance benchmarks for processing records
#
# By: Bast
"""Performance benchmarks for the processing records (``ProcessDataToClient`` and friends).

Every line that reaches or leaves the proxy is wrapped in a processing record, so creating
one, executing it and recording an update on it are on the hot path.

Like the NetworkDataLine benchmarks, each one uses ``benchmark.pedantic`` with fixed
``rounds`` and ``iterations=1``, so the records manager's retention does not change the cost
between runs. The ``NetworkData`` each record wraps is built in ``setup``, outside the timed
call. The 15-line message matches the default ``max_lines_to_process``.

The benchmarks run under ``tracking_actor("bench")``, as the proxy does. With benchmarks
enabled (``doit benchmark``) the ``addupdate`` benchmark asserts the ADR-0005 target of at
most 20 us per update; a disabled run (``doit check``, CI tests) skips the assertion. The
create and call benchmarks are informational.
"""

from typing import Any

import pytest

from bastproxy.libs.records.rtypes.clientdata import ProcessDataToClient
from bastproxy.libs.records.rtypes.networkdata import NetworkData, NetworkDataLine
from bastproxy.libs.records.tracking import tracking_actor

DEFAULT_LINES = 15
ROUNDS = 200
UPDATE_TARGET_SECONDS = 20e-6  # per addupdate


class _NoopToClient(ProcessDataToClient):
    """A ProcessDataToClient whose execution does nothing, so only the framework is timed."""

    def _exec_(self) -> None:
        """Do nothing."""


def _build_message() -> NetworkData:
    """Build a NetworkData holding DEFAULT_LINES lines."""
    with tracking_actor("bench"):
        return NetworkData(
            [NetworkDataLine(f"line {i}", originated="mud") for i in range(DEFAULT_LINES)]
        )


def _setup_message() -> tuple[tuple[NetworkData], dict[str, Any]]:
    """Per-round setup for ``benchmark.pedantic``: one fresh message, not timed."""
    return (_build_message(),), {}


@pytest.mark.benchmark
def test_bench_processing_record_create(benchmark: Any) -> None:
    """Benchmark creating one ProcessDataToClient around a 15-line message (informational)."""

    def create(message: NetworkData) -> ProcessDataToClient:
        with tracking_actor("bench"):
            return ProcessDataToClient(message)

    result = benchmark.pedantic(create, setup=_setup_message, rounds=ROUNDS, iterations=1)
    assert isinstance(result, ProcessDataToClient)
    assert len(result.message) == DEFAULT_LINES


@pytest.mark.benchmark
def test_bench_processing_record_create_and_call(benchmark: Any) -> None:
    """Benchmark creating and executing one record with a no-op ``_exec_`` (informational)."""

    def create_and_call(message: NetworkData) -> _NoopToClient:
        with tracking_actor("bench"):
            record = _NoopToClient(message)
            record()
        return record

    result = benchmark.pedantic(create_and_call, setup=_setup_message, rounds=ROUNDS, iterations=1)
    assert not result.executing
    assert result.execute_time_taken >= 0


@pytest.mark.benchmark
def test_bench_processing_record_addupdate(benchmark: Any) -> None:
    """Benchmark one ``addupdate`` on a processing record."""
    record = ProcessDataToClient(_build_message())

    def add() -> None:
        with tracking_actor("bench"):
            record.addupdate("Info", "bench update")

    benchmark.pedantic(add, rounds=ROUNDS, iterations=1)
    assert record.updates
    if not benchmark.disabled:
        median = benchmark.stats.stats.median
        assert median <= UPDATE_TARGET_SECONDS, f"{median * 1e6:.1f} us per addupdate"
