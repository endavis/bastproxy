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

The RecordManager keeps up to 5000 records per type in memory, so a benchmark
that creates records without bound would change cost as the store fills and
make runs incomparable. Each benchmark therefore uses ``benchmark.pedantic``
with fixed ``rounds`` and ``iterations=1``, keeping the records one test
creates (rounds x ``DEFAULT_LINES``) well under that limit. Lines per round
match the default ``max_lines_to_process`` of 15.
"""

from collections.abc import Callable, Iterator
from typing import Any

import pytest

from bastproxy.libs.api import API
from bastproxy.libs.records.rtypes.networkdata import NetworkData, NetworkDataLine

DEFAULT_LINES = 15
ROUNDS = 20
CHANGE_ROUNDS = 200


def _get_keys_from_dict(d: dict[Any, Any]) -> list[Any]:
    """Stand-in for plugins.core.utils:get.keys.from.dict."""
    keys: list[Any] = []
    for k, v in d.items():
        keys.append(k)
        if isinstance(v, dict):
            keys.extend(_get_keys_from_dict(v))
    return keys


def _dedent_list_of_strings(list_of_strings: list[str]) -> list[str]:
    """Stand-in for plugins.core.utils:dedent.list.of.strings."""
    if not list_of_strings:
        return list_of_strings
    new_data = [list_of_strings[0].lstrip()]
    diff = len(list_of_strings[0]) - len(new_data[0])
    new_data.extend(line[diff:] for line in list_of_strings[1:])
    return new_data


def _get_current_command_args() -> dict[str, Any]:
    """Stand-in for plugins.core.commands:get.current.command.args (no command running)."""
    return {}


STAND_IN_APIS: dict[str, Callable[..., Any]] = {
    "plugins.core.utils:get.keys.from.dict": _get_keys_from_dict,
    "plugins.core.utils:dedent.list.of.strings": _dedent_list_of_strings,
    "plugins.core.commands:get.current.command.args": _get_current_command_args,
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
    result = benchmark.pedantic(_create_lines, rounds=ROUNDS, iterations=1)
    assert len(result) == DEFAULT_LINES
    assert result[0].line == "line 0"


@pytest.mark.benchmark
def test_bench_networkdataline_attribute_change(benchmark: Any) -> None:
    """Benchmark changing the monitored ``line`` attribute on one record."""
    line = NetworkDataLine("line", originated="mud")
    values = ["changed a", "changed b"]
    state = {"n": 0}

    def change() -> str | bytes | bytearray:
        state["n"] += 1
        line.line = values[state["n"] % 2]
        return line.line

    result = benchmark.pedantic(change, rounds=CHANGE_ROUNDS, iterations=1)
    assert result in values
    assert line.line_modified


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
