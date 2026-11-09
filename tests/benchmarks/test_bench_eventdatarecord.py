# Project: bastproxy
# Filename: tests/benchmarks/test_bench_eventdatarecord.py
#
# File Description: Performance benchmarks for EventDataRecord
#
# By: Bast
"""Performance benchmarks for ``EventDataRecord`` (#246).

Informational, with no gate: the ADR-0005 targets are per line, not per event record.
Each benchmark uses ``benchmark.pedantic`` with fixed rounds and ``iterations=1`` so the
record store does not change the cost between runs, and runs under ``tracking_actor("bench")``
as the proxy does.
"""

from typing import Any

import pytest

from bastproxy.libs.records.rtypes.networkdata import NetworkDataLine
from bastproxy.libs.records.tracking import tracking_actor
from bastproxy.plugins.core.events.libs.data._event import EventDataRecord

DEFAULT_LINES = 15
ROUNDS = 50


@pytest.mark.benchmark
def test_bench_eventdatarecord_create(benchmark: Any) -> None:
    """Benchmark creating an EventDataRecord with 3 keys."""

    def create() -> EventDataRecord:
        with tracking_actor("bench"):
            return EventDataRecord(event_name="ev_bench", data={"a": "1", "b": "2", "c": "3"})

    result = benchmark.pedantic(create, rounds=ROUNDS, iterations=1)
    assert result["a"] == "1"


@pytest.mark.benchmark
def test_bench_eventdatarecord_set_line(benchmark: Any) -> None:
    """Benchmark setting a NetworkDataLine value."""
    record = EventDataRecord(event_name="ev_bench", data={})
    line = NetworkDataLine("line", originated="mud")

    def set_line() -> None:
        with tracking_actor("bench"):
            record["line"] = line

    benchmark.pedantic(set_line, rounds=ROUNDS, iterations=1)
    assert record["line"] is line


@pytest.mark.benchmark
def test_bench_eventdatarecord_line_cycle(benchmark: Any) -> None:
    """Benchmark the data_list cycle: one record, ``line`` set once per line."""
    lines = [NetworkDataLine(f"line {i}", originated="mud") for i in range(DEFAULT_LINES)]

    def cycle() -> EventDataRecord:
        with tracking_actor("bench"):
            record = EventDataRecord(event_name="ev_bench", data={})
            for line in lines:
                record["line"] = line
            return record

    result = benchmark.pedantic(cycle, rounds=ROUNDS, iterations=1)
    assert result["line"] is lines[-1]
