"""Tests for retaining records by root tree and evicting whole trees (#249, #233, #229)."""

import gc
import logging
import tracemalloc
import weakref
from collections.abc import Iterator
from typing import Any

import pytest

from bastproxy.libs.api import API
from bastproxy.libs.records.managers import records as records_module
from bastproxy.libs.records.managers.records import RMANAGER
from bastproxy.libs.records.rtypes.base import BaseRecord
from bastproxy.libs.records.rtypes.networkdata import NetworkData, NetworkDataLine
from bastproxy.plugins.core.events.libs.data._event import EventDataRecord
from bastproxy.plugins.core.events.plugin._event import Event

# Allowed growth of the traced heap over 400 rounds past the cap: noise, not retention.
FLAT_TOLERANCE_BYTES = 256 * 1024


class _Round(BaseRecord):
    """A stand-in for ProcessDataToClient: a root that owns a NetworkData of lines."""

    def __init__(self, lines: int = 3) -> None:
        super().__init__()
        self.lines = lines
        self.message: NetworkData | None = None

    def _exec_(self) -> None:
        message = NetworkData([NetworkDataLine(f"line {i}") for i in range(self.lines)])
        message.add_parent(self, reset=True)
        self.message = message


@pytest.fixture(autouse=True)
def isolated_manager(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    """Give each test an empty store and restore the manager settings afterwards."""
    monkeypatch.setattr(RMANAGER, "record_instances", {})
    monkeypatch.setattr(RMANAGER, "records", {})
    monkeypatch.setattr(RMANAGER, "max_trees", RMANAGER.max_trees)
    monkeypatch.setattr(RMANAGER, "max_changes", RMANAGER.max_changes)
    monkeypatch.setattr(RMANAGER, "_roots_since_prune", 0)
    api = API("test249")
    api.add("plugins.core.settings", "setting.get", lambda *_a, **_k: False, description="stand-in")
    saved = Event.MAX_RAISED_EVENTS
    Event.MAX_RAISED_EVENTS = 0
    try:
        yield
    finally:
        Event.MAX_RAISED_EVENTS = saved
        API._class_api.pop("plugins.core.settings:setting.get", None)


def _run_round(lines: int = 3) -> _Round:
    record = _Round(lines)
    record()
    return record


def _tree(record: _Round) -> list[Any]:
    assert record.message is not None
    return [record, record.message, *list(record.message)]


def _stored(record: Any) -> bool:
    by_type = RMANAGER.records.get(record.__class__.__name__, {})
    return record.uuid in RMANAGER.record_instances and record.uuid in by_type


def _gone(record: Any) -> bool:
    by_type = RMANAGER.records.get(record.__class__.__name__, {})
    return record.uuid not in RMANAGER.record_instances and record.uuid not in by_type


def _raise(name: str, data: Any) -> Any:
    raised = Event(name, created_by="test249").raise_event(data, "test249")
    assert raised is not None
    return raised


def test_oldest_tree_is_evicted_whole() -> None:
    RMANAGER.max_trees = 2
    rounds = [_run_round() for _ in range(3)]
    RMANAGER.prune()
    assert all(_gone(rec) for rec in _tree(rounds[0]))
    for kept in rounds[1:]:
        assert all(_stored(rec) for rec in _tree(kept))
        assert RMANAGER.get_record(kept.uuid) is kept


def test_shared_node_survives_until_every_tree_is_gone() -> None:
    RMANAGER.max_trees = 2
    first = _raise("ev_test249_first", {"x": 1})
    shared = first.event_data
    second = _raise("ev_test249_second", shared)
    assert isinstance(shared, EventDataRecord)
    assert shared.parents == [first, second]
    child = NetworkData([])
    child.add_parent(shared, reset=True)
    assert child in RMANAGER.get_children(shared) or shared in child.parents
    _run_round()
    RMANAGER.prune()
    assert _gone(first)
    assert _stored(second)
    assert _stored(shared)
    assert _stored(child)
    assert shared.parents == [first, second]
    _run_round()
    _run_round()
    RMANAGER.prune()
    assert _gone(second)
    assert _gone(shared)
    assert _gone(child)


def test_executing_root_is_protected() -> None:
    RMANAGER.max_trees = 1
    running = _Round()
    running.executing = True
    _run_round()
    _run_round()
    RMANAGER.prune()
    assert _stored(running)


def test_root_with_a_descendant_on_the_active_stack_is_protected() -> None:
    RMANAGER.max_trees = 1
    old = _run_round()
    assert old.message is not None
    deep = old.message[0]
    RMANAGER.start(deep)
    try:
        _run_round()
        _run_round()
        RMANAGER.prune()
        assert all(_stored(rec) for rec in _tree(old))
    finally:
        RMANAGER.end(deep)
    _run_round()
    RMANAGER.prune()
    assert all(_gone(rec) for rec in _tree(old))


def test_pending_records_are_not_counted_and_survive_tree_pruning() -> None:
    RMANAGER.max_trees = 1
    orphan = NetworkData([])
    assert RMANAGER.root_count() == 0
    _run_round()
    _run_round()
    RMANAGER.prune()
    assert RMANAGER.root_count() == 1
    assert _stored(orphan)


def test_pending_cap_evicts_the_oldest(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(records_module, "MAX_PENDING", 2)
    orphans = [NetworkData([]) for _ in range(3)]
    RMANAGER.prune()
    assert _gone(orphans[0])
    assert _stored(orphans[1])
    assert _stored(orphans[2])


def test_adopted_pending_record_joins_the_tree_of_its_root() -> None:
    RMANAGER.max_trees = 1
    orphan = NetworkData([])
    holder = _Round()
    orphan.add_parent(holder, reset=True)
    holder()
    _run_round()
    RMANAGER.prune()
    assert _gone(holder)
    assert _gone(orphan)


def test_dangling_record_is_evicted() -> None:
    root = _run_round()
    assert root.message is not None
    line = root.message[0]
    RMANAGER._remove(root)
    RMANAGER._remove(root.message)
    RMANAGER.prune()
    assert _gone(line)


def test_empty_network_data_in_an_evicted_tree_is_removed() -> None:
    """#229: an empty record is falsy and was left in record_instances."""
    RMANAGER.max_trees = 1
    old = _Round(0)
    old()
    assert old.message is not None
    assert len(old.message) == 0
    assert _stored(old.message)
    _run_round()
    RMANAGER.prune()
    assert _gone(old.message)
    assert "NetworkData" in RMANAGER.records
    assert old.message.uuid not in RMANAGER.records["NetworkData"]


def test_stores_agree_after_a_prune() -> None:
    RMANAGER.max_trees = 3
    for _ in range(8):
        _run_round()
    RMANAGER.prune()
    from_types = {uid for by_type in RMANAGER.records.values() for uid in by_type}
    assert from_types == set(RMANAGER.record_instances)


def test_get_records_returns_the_newest_oldest_first() -> None:
    rounds = [_run_round(0) for _ in range(5)]
    assert RMANAGER.get_records("_Round", 3) == rounds[-3:]
    assert RMANAGER.get_records("NoSuchType") is None
    assert dict(RMANAGER.get_types())["_Round"] == 5


def test_automatic_prune_bounds_the_roots() -> None:
    RMANAGER.max_trees = 5
    for _ in range(10):
        _run_round()
    assert RMANAGER.root_count() <= 6


def test_count_plateaus() -> None:
    RMANAGER.max_trees = 5
    sizes: dict[int, int] = {}
    for i in range(1, 301):
        _run_round()
        sizes[i] = len(RMANAGER.record_instances)
    per_tree = 1 + 1 + 3
    assert abs(sizes[300] - sizes[100]) <= per_tree
    assert sizes[300] <= 6 * per_tree


def test_traced_memory_is_flat_past_the_cap() -> None:
    """Once the tree cap is reached, more rounds do not grow the traced heap (#233)."""
    RMANAGER.max_trees = 10
    for _ in range(100):
        _run_round(lines=15)
    gc.collect()
    tracemalloc.start()
    try:
        for _ in range(100):
            _run_round(lines=15)
        gc.collect()
        settled, _ = tracemalloc.get_traced_memory()
        for _ in range(400):
            _run_round(lines=15)
        gc.collect()
        after, _ = tracemalloc.get_traced_memory()
    finally:
        tracemalloc.stop()
    # Before #249 the store grew by about 0.66 MB per 15-line round; 400 rounds would add ~260 MB.
    assert after - settled < FLAT_TOLERANCE_BYTES


def test_evicted_records_are_freed() -> None:
    RMANAGER.max_trees = 1
    old = _run_round()
    refs = [weakref.ref(rec) for rec in _tree(old)]
    del old
    _run_round()
    RMANAGER.prune()
    gc.collect()
    assert all(ref() is None for ref in refs)


def test_set_max_trees_clamps_and_prunes(caplog: pytest.LogCaptureFixture) -> None:
    RMANAGER.max_trees = 10
    rounds = [_run_round() for _ in range(4)]
    RMANAGER.set_max_trees(2)
    assert _gone(rounds[0])
    assert _gone(rounds[1])
    assert _stored(rounds[3])
    with caplog.at_level(logging.WARNING):
        RMANAGER.set_max_trees(0)
    assert RMANAGER.max_trees == 1
    assert "below 1" in caplog.text
    assert _gone(rounds[2])


def test_set_max_changes_applies_to_new_records(caplog: pytest.LogCaptureFixture) -> None:
    RMANAGER.set_max_changes(5)
    line = NetworkDataLine("x")
    message = NetworkData([])
    data = EventDataRecord(owner_id="test249")
    for i in range(20):
        line.line = f"t{i}"
        message.append(NetworkDataLine(f"l{i}"))
        data[f"k{i}"] = i
    assert len(line.tracking_changes()) == 5
    assert len(message.tracking_changes()) == 5
    assert len(data.tracking_changes()) == 5
    assert BaseRecord()._updates.maxlen == 5
    with caplog.at_level(logging.WARNING):
        RMANAGER.set_max_changes(-1)
    assert RMANAGER.max_changes == 0
    assert "negative" in caplog.text
