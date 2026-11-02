"""Tests for UpdateManager's bounded deque and uid_mapping."""

from dataclasses import dataclass

from bastproxy.libs.records.managers.updates import UpdateManager


@dataclass
class _FakeUpdate:
    """Stand-in update with only the attribute UpdateManager uses."""

    uuid: str


def test_eviction_trims_uid_mapping() -> None:
    """Adding past maxlen drops the oldest update from uid_mapping too."""
    updates = UpdateManager()
    items = [_FakeUpdate(uuid=f"u{i}") for i in range(1001)]
    for item in items:
        updates.add(item)

    assert len(updates) == 1000
    assert len(updates.uid_mapping) == len(updates)
    assert updates.get_update(items[0].uuid) is None
    for item in items[1:]:
        assert updates.get_update(item.uuid) is item


def test_under_capacity_keeps_everything() -> None:
    """Below maxlen nothing is evicted from the deque or the mapping."""
    updates = UpdateManager()
    items = [_FakeUpdate(uuid=f"u{i}") for i in range(10)]
    for item in items:
        updates.add(item)

    assert len(updates) == 10
    assert len(updates.uid_mapping) == 10
    for item in items:
        assert updates.get_update(item.uuid) is item


def test_exactly_at_capacity_keeps_everything() -> None:
    """Filling to exactly maxlen evicts nothing."""
    updates = UpdateManager()
    items = [_FakeUpdate(uuid=f"u{i}") for i in range(1000)]
    for item in items:
        updates.add(item)

    assert len(updates) == 1000
    assert len(updates.uid_mapping) == 1000
    assert updates.get_update(items[0].uuid) is items[0]
