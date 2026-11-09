"""Tests for BaseRecord as a plain node with capped, context-aware updates (#248)."""

import traceback
from collections.abc import Iterator
from typing import Any

import pytest

from bastproxy.libs.api import API
from bastproxy.libs.context import raised_event
from bastproxy.libs.records.events import RECORD_EVENTS
from bastproxy.libs.records.managers.records import RMANAGER
from bastproxy.libs.records.rtypes.base import BaseRecord
from bastproxy.libs.records.rtypes.clientdata import (
    ProcessDataToClient,
    SendDataDirectlyToClient,
)
from bastproxy.libs.records.rtypes.muddata import ProcessDataToMud, SendDataDirectlyToMud
from bastproxy.libs.records.rtypes.networkdata import NetworkData, NetworkDataLine
from bastproxy.libs.records.tracking import tracking_actor

_MESSAGE_LINES = 3


@pytest.fixture(autouse=True)
def _restore_manager(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    monkeypatch.setattr(RMANAGER, "capture_stacks", False)
    monkeypatch.setattr(RMANAGER, "max_changes", RMANAGER.max_changes)
    yield


def _keys(d: dict[Any, Any]) -> list[Any]:
    """Stand-in for plugins.core.utils:dict.key.list."""
    keys: list[Any] = []
    for key, value in d.items():
        keys.append(key)
        if isinstance(value, dict):
            keys.extend(_keys(value))
    return keys


@pytest.fixture(autouse=True)
def _plugin_apis() -> Iterator[None]:
    """Give the class-wide API the one plugin API the tree walk calls, then remove it."""
    API("test248").add("plugins.core.utils", "dict.key.list", _keys, description="stand-in")
    yield
    API._class_api.pop("plugins.core.utils:dict.key.list", None)


def _message() -> NetworkData:
    return NetworkData([NetworkDataLine(f"l{i}", originated="mud") for i in range(_MESSAGE_LINES)])


def test_base_record_is_a_plain_node() -> None:
    assert "AttributeMonitor" not in [cls.__name__ for cls in BaseRecord.__mro__]
    assert "__setattr__" not in vars(BaseRecord)
    record = BaseRecord()
    record.anything = 1  # type: ignore[attr-defined]
    assert record.updates == []


def test_construction_and_addupdate_make_no_api_call(monkeypatch: pytest.MonkeyPatch) -> None:
    def fail(self: API, api_location: str) -> Any:
        raise AssertionError(f"unexpected api call {api_location}")

    monkeypatch.setattr(API, "__call__", fail)
    record = BaseRecord()
    record.addupdate("Info", "x", extra={"k": "v"})
    assert [update.action for update in record.updates] == ["x"]


def test_no_stack_is_captured_while_capture_is_off(monkeypatch: pytest.MonkeyPatch) -> None:
    def fail(*_a: Any, **_k: Any) -> Any:
        raise AssertionError("traceback.format_stack called")

    monkeypatch.setattr(traceback, "format_stack", fail)
    record = BaseRecord()
    record.addupdate("Info", "x")
    assert record.stack_at_creation == []
    assert record.updates[-1].stack == []


def test_stacks_are_captured_while_capture_is_on() -> None:
    RMANAGER.set_capture_stacks(True)
    record = BaseRecord()
    record.addupdate("Info", "x")
    assert record.stack_at_creation
    assert record.updates[-1].stack
    assert any(
        "test_stacks_are_captured_while_capture_is_on" in line for line in record.updates[-1].stack
    )


def test_details_say_when_the_stack_was_not_captured() -> None:
    record = BaseRecord()
    details = record.get_formatted_details(include_children_records=False)
    assert any(line.startswith("Call Stack at Creation : not captured") for line in details)
    assert "Updates :" in details


def test_update_actor_is_the_tracking_actor() -> None:
    record = BaseRecord()
    with tracking_actor("plugins.test248:cmd"):
        record.addupdate("Info", "x")
    assert record.updates[0].actor == "plugins.test248:cmd"


def test_update_actor_falls_back_to_the_caller_outside_the_records_package() -> None:
    record = BaseRecord()
    record.addupdate("Info", "y")
    expected = f"{__name__}:test_update_actor_falls_back_to_the_caller_outside_the_records_package"
    assert record.updates[0].actor == expected
    assert f"Actor           : {expected}" in record.updates[0].format_detailed()


class _NoOp(BaseRecord):
    def _exec_(self) -> None:
        pass


def _run_record(record: BaseRecord) -> None:
    record()


def test_update_actor_skips_frames_inside_the_records_package() -> None:
    record = _NoOp()
    _run_record(record)
    # the _exec_ start/finish updates are made inside BaseRecord.__call__; the actor is its caller
    assert {update.actor for update in record.updates} == {f"{__name__}:_run_record"}


def test_event_stack_is_recorded_on_the_record_and_its_updates() -> None:
    with raised_event("ev_x"):
        record = BaseRecord()
        record.addupdate("Info", "x")
    assert record.event_stack == ("ev_x",)
    assert record.updates[0].event_stack == ["ev_x"]
    assert any(line.endswith(": ev_x") for line in record.updates[0].format_detailed())
    assert "Extra" not in "".join(record.updates[0].format_detailed())


def test_updates_are_capped_by_the_manager() -> None:
    RMANAGER.max_changes = 5
    record = BaseRecord()
    assert record._updates.maxlen == 5
    for i in range(20):
        record.addupdate("Info", f"u{i}")
    assert [update.action for update in record.updates] == [f"u{i}" for i in range(15, 20)]


def test_reserved_extra_keys_are_renamed() -> None:
    record = BaseRecord()
    record.addupdate("Info", "x", extra={"actor": "someone", "action": "y"})
    update = record.updates[0]
    assert update.action == "x"
    assert update.extra == {"extra_actor": "someone", "extra_action": "y"}


def test_get_update_finds_own_and_child_updates() -> None:
    parent = ProcessDataToClient(_message())
    parent.addupdate("Info", "own")
    child_line = parent.message[0]
    with tracking_actor("t"):
        child_line.line = "changed"
    own = parent.updates[0]
    child_update = child_line.updates[-1]
    assert parent.get_update(own.uuid) == own
    assert parent.get_update(child_update.uuid) == child_update
    assert parent.get_update("nope") is None


def test_get_update_on_a_tracked_parent_finds_a_child_update() -> None:
    message = _message()
    line = message[0]
    with tracking_actor("t"):
        line.line = "changed"
    update = line.updates[-1]
    assert message.get_update(update.uuid) == update


def test_get_all_updates_includes_children_in_time_order() -> None:
    parent = ProcessDataToClient(_message())
    parent.addupdate("Info", "own")
    updates = parent.get_all_updates()
    assert parent.updates[0] in updates
    assert updates == sorted(updates)


@pytest.mark.parametrize(
    "record_cls",
    [ProcessDataToClient, SendDataDirectlyToClient, ProcessDataToMud, SendDataDirectlyToMud],
)
def test_constructors_do_not_register_events(
    monkeypatch: pytest.MonkeyPatch, record_cls: type
) -> None:
    def fail(self: API, api_location: str) -> Any:
        if api_location == "plugins.core.events:event.add":
            raise AssertionError("event.add called")
        return lambda *_a, **_k: None

    monkeypatch.setattr(API, "__call__", fail)
    record_cls(_message())


def test_record_events_cover_the_four_event_names() -> None:
    assert {spec.name for spec in RECORD_EVENTS} == {
        "ev_to_client_data_modify",
        "ev_to_client_data_read",
        "ev_to_mud_data_modify",
        "ev_to_mud_data_read",
    }
    assert all(spec.description and spec.arg_descriptions for spec in RECORD_EVENTS)
    assert ProcessDataToClient(_message()).modify_data_event_name == "ev_to_client_data_modify"
    assert SendDataDirectlyToMud(_message()).read_data_event_name == "ev_to_mud_data_read"
