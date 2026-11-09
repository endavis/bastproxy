"""Tests for the parents of an EventDataRecord (#246, #230)."""

from collections.abc import Iterator

import pytest

from bastproxy.libs.api import API
from bastproxy.libs.records.managers.records import RMANAGER
from bastproxy.plugins.core.events.libs.data._event import EventDataRecord
from bastproxy.plugins.core.events.plugin._event import Event


@pytest.fixture(autouse=True)
def stand_in_api() -> Iterator[None]:
    """Stand in for setting.get."""
    saved = Event.MAX_RAISED_EVENTS
    api = API("test246")
    api.add("plugins.core.settings", "setting.get", lambda *_a, **_k: False, description="stand-in")
    try:
        yield
    finally:
        Event.MAX_RAISED_EVENTS = saved
        API._class_api.pop("plugins.core.settings:setting.get", None)


def _event(name: str) -> Event:
    return Event(name, created_by="test246")


def test_one_event_is_the_only_parent() -> None:
    raised = _event("ev_test246_one").raise_event({"x": 1}, "test246")
    assert raised is not None
    assert raised.event_data.parent is raised
    assert raised.event_data.parents == [raised]


def test_shared_record_keeps_every_event_as_parent() -> None:
    first = _event("ev_test246_first").raise_event({"x": 1}, "test246")
    assert first is not None
    record = first.event_data
    second = _event("ev_test246_second").raise_event(record, "test246")
    assert second is not None
    assert second.event_data is record
    assert record.parents == [first, second]
    assert record.parent is first
    assert record in RMANAGER.get_children(first)
    assert record in RMANAGER.get_children(second)
    for raised in (first, second):
        assert any(record.uuid in line for line in RMANAGER.format_all_children(raised))


def test_data_list_uses_one_record_and_one_update_per_item() -> None:
    event = _event("ev_test246_list")
    raised = event.raise_event({}, "test246", data_list=["a", "b", "c"], key_name="line")
    assert raised is not None
    record = raised.event_data
    assert isinstance(record, EventDataRecord)
    assert record.parents == [raised]
    assert record["line"] == "c"
    sets = [u for u in record.updates if u.flag == "Modify"]
    assert len(sets) == 3
