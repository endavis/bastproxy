# Project: bastproxy
# Filename: tests/benchmarks/test_bench_api.py
#
# File Description: Performance benchmarks for the API call path
#
# By: Bast
"""Performance benchmarks for the API call path (issue #105).

Every plugin talks to every other through ``self.api("<toplevel>:<name>")(...)``.
One call is three steps: ``API.get`` looks the name up, ``APIItem.__call__``
walks the call stack with ``get_caller_owner_id`` to find who is calling, and
``StatsManager.add_call`` records the call. The cases below time each step on
its own and then the whole path, so the cost of the stack walk and of the
unknown-caller path can be read off the results.

No plugins are loaded in a unit-level benchmark, so a fixture registers one
class API and one instance API under ``bench.api`` and removes them, and their
stats, afterwards.

Only the unknown-caller case creates ``LogRecord`` objects (a stack dump per
call). The RecordManager keeps up to 5000 records per type in memory, so that
case uses ``benchmark.pedantic`` with fixed ``rounds`` and ``iterations=1``.
"""

from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any

import pytest

from bastproxy.libs.api import API
from bastproxy.libs.api._apistats import STATS_MANAGER
from bastproxy.libs.api._functools import get_caller_owner_id
from bastproxy.libs.exceptions import APINotFoundError

TOPLEVEL = "bench.api"
CLASS_API = f"{TOPLEVEL}:x"
INSTANCE_API = f"{TOPLEVEL}:y"
MISSING_API = f"{TOPLEVEL}:missing"
OWNER_ID = "bench.owner"
NEST_DEPTH = 20
UNKNOWN_ROUNDS = 50


def _class_function(value: int) -> int:
    """Return the value plus one; the class API under test."""
    return value + 1


def _instance_function(value: int) -> int:
    """Return the value plus two; the instance API under test."""
    return value + 2


@contextmanager
def _registered_apis() -> Iterator[API]:
    """Register one class and one instance API under ``bench.api``, then remove them."""
    api = API(owner_id=OWNER_ID)
    api.add(TOPLEVEL, "x", _class_function, description="benchmark class api")
    api.add(TOPLEVEL, "y", _instance_function, instance=True, description="benchmark instance api")
    try:
        yield api
    finally:
        for key in [k for k in API._class_api if k.startswith(f"{TOPLEVEL}:")]:
            del API._class_api[key]
        for key in [k for k in STATS_MANAGER.stats if k.startswith(f"{TOPLEVEL}:")]:
            del STATS_MANAGER.stats[key]


@pytest.fixture
def bench_api() -> Iterator[API]:
    """Yield an API object with the ``bench.api`` APIs registered."""
    with _registered_apis() as api:
        yield api


class Owner:
    """A caller with an ``owner_id``, so the stack walk can stop at it."""

    def __init__(self, api: API) -> None:
        self.owner_id = OWNER_ID
        self.api = api

    def call(self) -> int:
        """Call the class API from the owner's own frame."""
        return int(self.api(CLASS_API)(1))

    def call_nested(self, depth: int) -> int:
        """Call the class API from ``depth`` plain frames below this method."""
        return _nested_call(self.api, depth)

    def caller_id(self) -> str:
        """Return what get_caller_owner_id finds from this frame."""
        return get_caller_owner_id()


def _nested_call(api: API, depth: int) -> int:
    """Recurse ``depth`` frames (none has ``self``), then call the class API."""
    if depth == 0:
        return int(api(CLASS_API)(1))
    return _nested_call(api, depth - 1)


def _module_level_call(api: API) -> int:
    """Call the class API from a frame chain that has no owner (the unknown-caller path)."""
    return int(api(CLASS_API)(1))


def _lookup_miss(api: API) -> bool:
    """Look up a name that is not registered."""
    with pytest.raises(APINotFoundError):
        api.get(MISSING_API)
    return True


def test_bench_registry_is_cleaned_up() -> None:
    """The fixture leaves no ``bench.api`` key in the registry or in the stats."""
    with _registered_apis() as api:
        owner = Owner(api)
        assert owner.call() == 2
        assert f"{TOPLEVEL}:x" in API._class_api
        assert f"{TOPLEVEL}:x" in STATS_MANAGER.stats
    assert not [k for k in API._class_api if k.startswith(f"{TOPLEVEL}:")]
    assert not [k for k in STATS_MANAGER.stats if k.startswith(f"{TOPLEVEL}:")]


@pytest.mark.benchmark
def test_bench_api_baseline_direct_call(benchmark: Any) -> None:
    """(a) Baseline: call the function directly, with no API."""
    result = benchmark(_class_function, 1)
    assert result == 2


@pytest.mark.benchmark
def test_bench_api_get_class_hit(benchmark: Any, bench_api: API) -> None:
    """(b) ``API.get`` for a class API: an instance-dict miss, then a class-dict hit."""
    item = benchmark(bench_api.get, CLASS_API)
    assert item.tfunction is _class_function


@pytest.mark.benchmark
def test_bench_api_get_instance_hit(benchmark: Any, bench_api: API) -> None:
    """(c) ``API.get`` for an instance API: found in the first dict."""
    item = benchmark(bench_api.get, INSTANCE_API)
    assert item.tfunction is _instance_function


@pytest.mark.benchmark
def test_bench_api_get_miss(benchmark: Any, bench_api: API) -> None:
    """(d) ``API.get`` for an unknown name raises ``APINotFoundError`` (includes pytest.raises)."""
    assert benchmark(_lookup_miss, bench_api) is True


@pytest.mark.benchmark
def test_bench_api_full_call_known_caller(benchmark: Any, bench_api: API) -> None:
    """(e) Full ``api(name)(arg)`` from a method of an object with an ``owner_id``."""
    owner = Owner(bench_api)
    result = benchmark(owner.call)
    assert result == 2
    assert STATS_MANAGER.stats[CLASS_API].detailed_calls[OWNER_ID] > 0


@pytest.mark.benchmark
def test_bench_api_full_call_nested_caller(benchmark: Any, bench_api: API) -> None:
    """(f) The same call with the caller NEST_DEPTH plain frames below the owner frame."""
    owner = Owner(bench_api)
    result = benchmark(owner.call_nested, NEST_DEPTH)
    assert result == 2
    assert STATS_MANAGER.stats[CLASS_API].detailed_calls[OWNER_ID] > 0


@pytest.mark.benchmark
def test_bench_get_caller_owner_id(benchmark: Any, bench_api: API) -> None:
    """(g) ``get_caller_owner_id()`` alone, with the owner one frame up."""
    owner = Owner(bench_api)
    assert benchmark(owner.caller_id) == OWNER_ID


@pytest.mark.benchmark
def test_bench_stats_add_call(benchmark: Any, bench_api: API) -> None:
    """(h) ``STATS_MANAGER.add_call`` alone, for a known caller."""
    before = STATS_MANAGER.stats[CLASS_API].count if CLASS_API in STATS_MANAGER.stats else 0
    benchmark(STATS_MANAGER.add_call, CLASS_API, OWNER_ID)
    assert STATS_MANAGER.stats[CLASS_API].count > before


@pytest.mark.benchmark
def test_bench_api_full_call_unknown_caller(benchmark: Any, bench_api: API) -> None:
    """(i) Full call with no owner on the stack: a warning, a stack dump and a LogRecord."""
    result = benchmark.pedantic(
        _module_level_call, args=(bench_api,), rounds=UNKNOWN_ROUNDS, iterations=1
    )
    assert result == 2
    assert STATS_MANAGER.stats[CLASS_API].detailed_calls["unknown"] > 0


@pytest.mark.benchmark
def test_bench_api_construct(benchmark: Any) -> None:
    """(j) Build an ``API`` object; each one registers 14 instance APIs."""
    api = benchmark(API, owner_id="bench")
    assert isinstance(api, API)
    assert len(api._instance_api) == 14
