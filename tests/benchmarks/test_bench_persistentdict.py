# Project: bastproxy
# Filename: tests/benchmarks/test_bench_persistentdict.py
#
# File Description: Performance benchmarks for persistentdict conversion helpers
#
# By: Bast
"""Performance benchmarks for the persistentdict conversion helpers.

``convert`` and ``convert_keys_to_int`` run on every settings load, so their
cost scales with the size of each plugin's saved data.
"""

from typing import Any

import pytest

from bastproxy.libs.persistentdict import convert, convert_keys_to_int


def _nested_data(width: int, depth: int) -> dict[str, Any]:
    """Build a nested dict with string keys that look like integers."""
    if depth == 0:
        return {str(i): f"value{i}" for i in range(width)}
    return {str(i): _nested_data(width, depth - 1) for i in range(width)}


@pytest.mark.benchmark
def test_bench_convert_keys_to_int_flat(benchmark: Any) -> None:
    """Benchmark convert_keys_to_int() on a flat 1000-key dict."""
    data = _nested_data(1000, 0)
    result = benchmark(convert_keys_to_int, data)
    assert 0 in result


@pytest.mark.benchmark
def test_bench_convert_keys_to_int_nested(benchmark: Any) -> None:
    """Benchmark convert_keys_to_int() on a 10x10x10 nested dict."""
    data = _nested_data(10, 2)
    result = benchmark(convert_keys_to_int, data)
    assert 0 in result[0][0]


@pytest.mark.benchmark
def test_bench_convert_nested(benchmark: Any) -> None:
    """Benchmark convert() on a 10x10x10 nested dict with mixed values."""
    data: dict[str, Any] = _nested_data(10, 2)
    data["bytes"] = b"raw"
    data["list"] = [b"a", "b", {"c": b"d"}]
    result = benchmark(convert, data)
    assert result["bytes"] == "b'raw'"
