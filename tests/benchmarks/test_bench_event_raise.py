# Project: bastproxy
# Filename: tests/benchmarks/test_bench_event_raise.py
#
# File Description: Benchmarks for raising an event and reading the event stack
#
# By: Bast
"""Benchmark what raising an event costs (audit #107, Q4).

Informational, with no gate. Each benchmark raises through a real ``Event``, which builds the
``EventDataRecord`` and ``ProcessRaisedEvent`` records the live path builds, under
``tracking_actor`` as the proxy does. The record store is replaced by an empty one for the run and
restored afterwards. ``setting.get`` is stubbed to return False, so the ``log_savestate`` lookup
costs one stand-in call.

Cases:

1. a raise with no callbacks;
2. a raise with 10 no-op callbacks over 3 priorities;
3. a raise over a ``data_list`` of 15 items with ``key_name="line"``;
4. a raise when ``raised_events`` is already at ``MAX_RAISED_EVENTS``;
5. reading the event stack at depth 1 and depth 10.

Every callback has its own owner id, so the duplicate registration check (ES-5 in
``docs/claude/event_system_findings.md``) never matches. No callback raises an event, so the
nested raise reset (ES-7) does not apply. The per-round cost of a whole MUD to client round, with
the store at its cap, is in ``test_bench_retention.py``.
"""

from collections.abc import Iterator
from contextlib import ExitStack
from typing import Any

import pytest

from bastproxy.libs.api import API
from bastproxy.libs.context import event_stack, raised_event
from bastproxy.libs.records.managers.records import RMANAGER
from bastproxy.libs.records.rtypes.networkdata import NetworkDataLine
from bastproxy.libs.records.tracking import tracking_actor
from bastproxy.plugins.core.events.plugin._event import Event

OWNER = "bench107"
ROUNDS = 200
CALLBACKS = 10
PRIORITIES = (10, 50, 90)
LINES = 15
DEEP = 10


class _Owner:
    """A plugin-like object with a no-op callback."""

    def __init__(self, plugin_id: str) -> None:
        self.plugin_id = plugin_id

    def cb(self) -> None:
        """Do nothing."""


@pytest.fixture
def clean_store() -> Iterator[None]:
    """Give the benchmark an empty record store and a stand-in ``setting.get``."""
    saved = (
        RMANAGER.record_instances,
        RMANAGER.records,
        RMANAGER.max_trees,
        RMANAGER._roots_since_prune,
    )
    RMANAGER.record_instances = {}
    RMANAGER.records = {}
    RMANAGER._roots_since_prune = 0
    api = API(OWNER)
    api.add("plugins.core.settings", "setting.get", lambda *_a, **_k: False, description="stub")
    try:
        yield
    finally:
        (
            RMANAGER.record_instances,
            RMANAGER.records,
            RMANAGER.max_trees,
            RMANAGER._roots_since_prune,
        ) = saved
        API._class_api.pop("plugins.core.settings:setting.get", None)


def _event_with_callbacks(name: str, count: int) -> tuple[Event, list[_Owner]]:
    """Build an event with ``count`` no-op callbacks spread over PRIORITIES."""
    event = Event(name, created_by=OWNER)
    owners = [_Owner(f"{OWNER}.owner{i}") for i in range(count)]
    for i, owner in enumerate(owners):
        event.register(owner.cb, owner.plugin_id, PRIORITIES[i % len(PRIORITIES)])
    return event, owners


def _raise(event: Event, **kwargs: Any) -> None:
    """Raise the event the way the events plugin does, under an actor."""
    with tracking_actor(OWNER):
        event.raise_event({"x": 1}, OWNER, **kwargs)


@pytest.mark.benchmark
@pytest.mark.usefixtures("clean_store")
def test_bench_raise_no_callbacks(benchmark: Any) -> None:
    """Benchmark a raise with nothing registered."""
    event = Event("ev_bench107_empty", created_by=OWNER)
    benchmark.pedantic(_raise, args=(event,), rounds=ROUNDS, iterations=1)
    assert event.raised_count >= 1


@pytest.mark.benchmark
@pytest.mark.usefixtures("clean_store")
def test_bench_raise_ten_callbacks(benchmark: Any) -> None:
    """Benchmark a raise with 10 no-op callbacks over 3 priorities."""
    event, owners = _event_with_callbacks("ev_bench107_ten", CALLBACKS)
    assert event.count() == CALLBACKS
    benchmark.pedantic(_raise, args=(event,), rounds=ROUNDS, iterations=1)
    assert len(owners) == CALLBACKS
    assert event.raised_count >= 1


@pytest.mark.benchmark
@pytest.mark.usefixtures("clean_store")
def test_bench_raise_data_list(benchmark: Any) -> None:
    """Benchmark a raise over a 15 item data_list with one callback."""
    event, _owners = _event_with_callbacks("ev_bench107_list", 1)
    with tracking_actor(OWNER):
        lines = [NetworkDataLine(f"line {i}", originated="mud") for i in range(LINES)]
    benchmark.pedantic(
        _raise, args=(event,), kwargs={"data_list": lines, "key_name": "line"}, rounds=ROUNDS
    )
    assert event.raised_count >= 1


@pytest.mark.benchmark
@pytest.mark.usefixtures("clean_store")
def test_bench_raise_history_full(benchmark: Any) -> None:
    """Benchmark a raise when raised_events is already at MAX_RAISED_EVENTS."""
    event, _owners = _event_with_callbacks("ev_bench107_full", 1)
    for _ in range(Event.MAX_RAISED_EVENTS):
        _raise(event)
    assert len(event.raised_events) == Event.MAX_RAISED_EVENTS
    benchmark.pedantic(_raise, args=(event,), rounds=ROUNDS, iterations=1)
    assert len(event.raised_events) == Event.MAX_RAISED_EVENTS


@pytest.mark.benchmark
def test_bench_event_stack_depth_1(benchmark: Any) -> None:
    """Benchmark reading the event stack with one event on it."""
    with raised_event("ev_bench107_a"):
        result = benchmark.pedantic(lambda: list(event_stack.get()), rounds=ROUNDS * 10)
    assert result == ["ev_bench107_a"]


@pytest.mark.benchmark
def test_bench_event_stack_depth_10(benchmark: Any) -> None:
    """Benchmark reading the event stack with ten events on it."""
    with ExitStack() as stack:
        for i in range(DEEP):
            stack.enter_context(raised_event(f"ev_bench107_{i}"))
        result = benchmark.pedantic(lambda: list(event_stack.get()), rounds=ROUNDS * 10)
    assert len(result) == DEEP
