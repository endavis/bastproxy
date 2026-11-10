"""Records and updates keep creation order when their timestamps tie (#320)."""

import datetime

from bastproxy.libs.records.rtypes.base import BaseRecord
from bastproxy.libs.records.rtypes.networkdata import NetworkDataLine

SAME = datetime.datetime(2026, 1, 1, tzinfo=datetime.UTC)
LATER = SAME + datetime.timedelta(seconds=1)


def test_base_record_ties_order_by_creation() -> None:
    first, second = BaseRecord(), BaseRecord()
    first.created = second.created = SAME
    assert sorted([second, first]) == [first, second]


def test_base_record_timestamp_beats_sequence() -> None:
    first, second = BaseRecord(), BaseRecord()
    first.created, second.created = LATER, SAME
    assert sorted([first, second]) == [second, first]


def test_tracked_record_ties_order_by_creation() -> None:
    first, second = NetworkDataLine("one"), NetworkDataLine("two")
    first._tracking_created = second._tracking_created = SAME
    assert first.created == second.created
    assert sorted([second, first]) == [first, second]


def test_tracked_record_timestamp_beats_sequence() -> None:
    first, second = NetworkDataLine("one"), NetworkDataLine("two")
    first._tracking_created, second._tracking_created = LATER, SAME
    assert sorted([first, second]) == [second, first]


def test_base_record_updates_tie_order_by_creation() -> None:
    record = BaseRecord()
    record.addupdate("Info", "one")
    record.addupdate("Info", "two")
    for entry in record._updates:
        entry.created_time = SAME
    first, second = record.updates
    assert first.time_taken == second.time_taken
    assert sorted([second, first]) == [first, second]


def test_tracked_update_timestamp_beats_sequence() -> None:
    record = BaseRecord()
    record.addupdate("Info", "one")
    record.addupdate("Info", "two")
    entry_one, entry_two = record._updates
    entry_one.created_time, entry_two.created_time = LATER, SAME
    first, second = record.updates
    assert sorted([first, second]) == [second, first]


def test_tracked_record_updates_tie_order_by_creation() -> None:
    line = NetworkDataLine("x")
    line.addupdate("Info", "one")
    line.addupdate("Info", "two")
    first, second = (u for u in line.updates if u.action in ("one", "two"))
    first.entry.created_time = second.entry.created_time = SAME
    assert sorted([second, first]) == [first, second]
