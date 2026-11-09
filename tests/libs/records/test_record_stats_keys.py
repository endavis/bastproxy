"""Tests that record API stats stay bounded as records are created (#232)."""

from collections.abc import Iterator

import pytest

from bastproxy.libs.api._apistats import STATS_MANAGER
from bastproxy.libs.records.rtypes.base import BaseRecord
from bastproxy.libs.records.rtypes.networkdata import NetworkDataLine

PREFIXES = ("UpdateRecord", "NetworkDataLine", "StatsProbe")


class StatsProbe(BaseRecord):
    """Plain record subclass used to exercise the default owner id."""


@pytest.fixture(autouse=True)
def _isolate_stats() -> Iterator[None]:
    """Restore the shared stats after every test."""
    snapshot = dict(STATS_MANAGER.stats)
    yield
    STATS_MANAGER.stats.clear()
    STATS_MANAGER.stats.update(snapshot)


def _record_keys() -> set[str]:
    keys: set[str] = set()
    for item in STATS_MANAGER.stats.values():
        keys.update(k for k in item.detailed_calls if k.startswith(PREFIXES))
    return keys


def _make_round(i: int) -> None:
    StatsProbe()
    NetworkDataLine(f"line {i}", originated="mud")


def test_record_caller_keys_do_not_grow() -> None:
    for i in range(5):
        _make_round(i)
    settled = _record_keys()
    for i in range(5, 25):
        _make_round(i)
    assert _record_keys() == settled
    assert len(settled) <= 8


def test_default_owner_id_is_class_name() -> None:
    first = StatsProbe()
    second = StatsProbe()
    assert first.owner_id == "StatsProbe"
    assert first.api.owner_id == "StatsProbe"
    assert first.uuid != second.uuid
    assert first != second


def test_explicit_owner_id_is_kept() -> None:
    assert BaseRecord(owner_id="plugins.x").owner_id == "plugins.x"


def test_networkdata_owner() -> None:
    line = NetworkDataLine("a")
    assert line.owner_id == "NetworkDataLine"


def test_addupdate_makes_no_api_call() -> None:
    def total_calls() -> int:
        return sum(item.count for item in STATS_MANAGER.stats.values())

    record = StatsProbe()
    before = total_calls()
    for _ in range(5):
        record.addupdate("Info", "x")
    assert total_calls() == before
    assert len(record.updates) == 5
