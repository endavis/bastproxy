"""Tests that record API stats stay bounded as records are created (#232)."""

from collections.abc import Iterator

import pytest

from bastproxy.libs.api._apistats import STATS_MANAGER
from bastproxy.libs.records.rtypes.base import BaseRecord
from bastproxy.libs.records.rtypes.log import LogRecord
from bastproxy.libs.records.rtypes.networkdata import NetworkDataLine
from bastproxy.libs.records.rtypes.update import UpdateRecord

PREFIXES = ("UpdateRecord", "NetworkDataLine", "LogRecord", "StatsProbe")


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
    LogRecord(f"msg {i}")
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


def test_networkdata_and_update_owner() -> None:
    line = NetworkDataLine("a")
    assert line.owner_id == "NetworkDataLine"
    update = UpdateRecord(line, "flag", "action")
    assert update.api.owner_id == "UpdateRecord"


def test_update_record_stats_grouped() -> None:
    def counts() -> tuple[int, int]:
        item = STATS_MANAGER.stats.get("libs.api:api.exists")
        if item is None:
            return (0, 0)
        return (
            item.calls_by_caller.get("UpdateRecord", 0),
            item.detailed_calls.get("UpdateRecord", 0),
        )

    before = counts()
    n = 5
    for i in range(n):
        NetworkDataLine(f"x {i}")
    after = counts()
    assert after[0] - before[0] >= n
    assert after[1] - before[1] >= n
    item = STATS_MANAGER.stats["libs.api:api.exists"]
    assert [k for k in item.detailed_calls if k.startswith("UpdateRecord")] == ["UpdateRecord"]
