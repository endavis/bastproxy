# Project: bastproxy
# Filename: tests/benchmarks/test_bench_networkdataline.py
#
# File Description: Performance benchmarks for NetworkDataLine and NetworkData records
#
# By: Bast
"""Performance benchmarks for the NetworkDataLine and NetworkData records.

Every line read from the mud or a client becomes a ``NetworkDataLine``, so
creating one, changing a monitored attribute and formatting a batch are on the
hot path.

The RecordManager keeps the last N root record trees in memory (100 by default)
and evicts older trees whole, so a benchmark that creates records without bound
would change cost as the store fills and make runs incomparable. Each benchmark
therefore uses ``benchmark.pedantic`` with fixed ``rounds`` and ``iterations=1``.
The lines it creates are parentless data holders, which the manager does not
count as trees, so it only trims them past its pending cap. Lines per round
match the default ``max_lines_to_process`` of 15.

Both records are built on pydatatracker (ADR-0006). The create and change benchmarks run
under ``tracking_actor("bench")``, as the proxy does, and assert the ADR-0005 targets when
benchmarks are enabled (``doit benchmark``): at most 50 us per line created and 20 us per
change. A disabled run (``doit check``, CI tests) skips the assertion. The lock benchmark is
informational.
"""

from collections.abc import Callable, Iterator
from typing import Any

import pytest

from bastproxy.libs.api import API
from bastproxy.libs.records.rtypes.networkdata import NetworkData, NetworkDataLine
from bastproxy.libs.records.tracking import tracking_actor

DEFAULT_LINES = 15
ROUNDS = 20
CHANGE_ROUNDS = 200
CREATE_TARGET_SECONDS = 50e-6  # per line created
CHANGE_TARGET_SECONDS = 20e-6  # per change


def _get_keys_from_dict(d: dict[Any, Any]) -> list[Any]:
    """Stand-in for plugins.core.utils:dict.key.list."""
    keys: list[Any] = []
    for k, v in d.items():
        keys.append(k)
        if isinstance(v, dict):
            keys.extend(_get_keys_from_dict(v))
    return keys


def _dedent_list_of_strings(list_of_strings: list[str]) -> list[str]:
    """Stand-in for plugins.core.utils:string.dedent."""
    if not list_of_strings:
        return list_of_strings
    new_data = [list_of_strings[0].lstrip()]
    diff = len(list_of_strings[0]) - len(new_data[0])
    new_data.extend(line[diff:] for line in list_of_strings[1:])
    return new_data


def _get_current_command_args() -> dict[str, Any]:
    """Stand-in for plugins.core.commands:command.current.args.get (no command running)."""
    return {}


STAND_IN_APIS: dict[str, Callable[..., Any]] = {
    "plugins.core.utils:dict.key.list": _get_keys_from_dict,
    "plugins.core.utils:string.dedent": _dedent_list_of_strings,
    "plugins.core.commands:command.current.args.get": _get_current_command_args,
}


@pytest.fixture
def plugin_apis() -> Iterator[None]:
    """Register the plugin APIs that get_formatted_details calls, then remove them.

    No plugins are loaded in a unit-level benchmark, so the class-wide API is
    given equivalent functions for the duration of the test.
    """
    api = API("benchmark")
    for full_name, func in STAND_IN_APIS.items():
        top, name = full_name.split(":")
        api.add(top, name, func, description="benchmark stand-in")
    try:
        yield
    finally:
        for full_name in STAND_IN_APIS:
            API._class_api.pop(full_name, None)


def _create_lines() -> list[NetworkDataLine]:
    """Create DEFAULT_LINES mud-originated lines."""
    return [NetworkDataLine(f"line {i}", originated="mud") for i in range(DEFAULT_LINES)]


def _build_network_data() -> NetworkData:
    """Build a NetworkData holding DEFAULT_LINES lines."""
    return NetworkData(_create_lines())


@pytest.mark.benchmark
def test_bench_networkdataline_create(benchmark: Any) -> None:
    """Benchmark creating DEFAULT_LINES NetworkDataLine records."""

    def create() -> list[NetworkDataLine]:
        with tracking_actor("bench"):
            return _create_lines()

    result = benchmark.pedantic(create, rounds=ROUNDS, iterations=1)
    assert len(result) == DEFAULT_LINES
    assert result[0].line == "line 0"
    if not benchmark.disabled:
        per_line = benchmark.stats.stats.median / DEFAULT_LINES
        assert per_line <= CREATE_TARGET_SECONDS, f"{per_line * 1e6:.1f} us per line created"


@pytest.mark.benchmark
def test_bench_networkdataline_attribute_change(benchmark: Any) -> None:
    """Benchmark changing the monitored ``line`` attribute on one record."""
    line = NetworkDataLine("line", originated="mud")
    values = ["changed a", "changed b"]
    state = {"n": 0}

    def change() -> str | bytes | bytearray:
        state["n"] += 1
        with tracking_actor("bench"):
            line.line = values[state["n"] % 2]
        return line.line

    result = benchmark.pedantic(change, rounds=CHANGE_ROUNDS, iterations=1)
    assert result in values
    assert line.line_modified
    if not benchmark.disabled:
        median = benchmark.stats.stats.median
        assert median <= CHANGE_TARGET_SECONDS, f"{median * 1e6:.1f} us per change"


@pytest.mark.benchmark
def test_bench_networkdata_build(benchmark: Any) -> None:
    """Benchmark building a NetworkData of DEFAULT_LINES lines."""
    result = benchmark.pedantic(_build_network_data, rounds=ROUNDS, iterations=1)
    assert len(result) == DEFAULT_LINES


@pytest.mark.benchmark
def test_bench_networkdata_get_formatted_details(benchmark: Any, plugin_apis: None) -> None:
    """Benchmark get_formatted_details() on a NetworkData of DEFAULT_LINES lines."""
    data = _build_network_data()
    result = benchmark.pedantic(data.get_formatted_details, rounds=ROUNDS, iterations=1)
    assert result
    assert result[0].endswith("NetworkData")


@pytest.mark.benchmark
def test_bench_networkdataline_lock(benchmark: Any) -> None:
    """Benchmark locking DEFAULT_LINES lines through their NetworkData (informational)."""
    built = [_build_network_data() for _ in range(ROUNDS)]
    pending = list(built)

    def lock() -> None:
        with tracking_actor("bench"):
            pending.pop().lock()

    benchmark.pedantic(lock, rounds=ROUNDS, iterations=1)
    # A disabled benchmark (doit check) runs lock() once, an enabled one ROUNDS times.
    done = built[len(pending) :]
    assert done
    assert all(data.locked for data in done)
