"""Tests for the undeclared-key warning in Event.raise_event (#466)."""

import logging
from collections.abc import Iterator
from typing import Any

import pytest

from bastproxy.libs.api import API
from bastproxy.plugins.core.events.libs.data._event import EventDataRecord
from bastproxy.plugins.core.events.plugin import _event
from bastproxy.plugins.core.events.plugin._event import Event


@pytest.fixture(autouse=True)
def settings_stub() -> Iterator[None]:
    """Stand in for the settings plugin api the raise path calls."""
    api = API("test466")
    api.add("plugins.core.settings", "setting.get", lambda *_a, **_k: False, description="stand-in")
    try:
        yield
    finally:
        API._class_api.pop("plugins.core.settings:setting.get", None)


@pytest.fixture
def warnings(monkeypatch: pytest.MonkeyPatch) -> list[tuple[Any, ...]]:
    """Capture the log_to calls made by the event module."""
    calls: list[tuple[Any, ...]] = []

    def fake_log_to(sources: Any, level: int, msg: str, *args: object, **_kw: Any) -> None:
        calls.append((level, msg, args))

    monkeypatch.setattr(_event, "log_to", fake_log_to)
    return calls


def _warned(calls: list[tuple[Any, ...]]) -> list[tuple[Any, ...]]:
    return [c for c in calls if c[0] == logging.WARNING]


def _make_event(arg_descriptions: dict[str, Any] | None) -> Event:
    return Event("ev_probe466", created_by="probe466", arg_descriptions=arg_descriptions)


def test_declared_keys_do_not_warn(warnings: list[tuple[Any, ...]]) -> None:
    event = _make_event({"a": "first", "b": "second"})
    assert event.raise_event({"a": 1}, "actor466") is not None
    assert _warned(warnings) == []


def test_undeclared_key_warns_once_and_still_raises(warnings: list[tuple[Any, ...]]) -> None:
    event = _make_event({"a": "first"})
    raised = event.raise_event({"a": 1, "z": 2, "y": 3}, "actor466")
    assert raised is not None
    found = _warned(warnings)
    assert len(found) == 1
    assert found[0][2] == ("ev_probe466", "actor466", "y, z")


def test_repeat_key_is_silent_and_new_key_warns_for_new_key_only(
    warnings: list[tuple[Any, ...]],
) -> None:
    event = _make_event({"a": "first"})
    event.raise_event({"z": 1}, "actor466")
    event.raise_event({"z": 1}, "actor466")
    assert len(_warned(warnings)) == 1
    event.raise_event({"z": 1, "w": 1}, "actor466")
    found = _warned(warnings)
    assert len(found) == 2
    assert found[1][2][2] == "w"


def test_dedup_is_per_event(warnings: list[tuple[Any, ...]]) -> None:
    first = _make_event({"a": "first"})
    second = Event("ev_other466", created_by="probe466", arg_descriptions={"a": "first"})
    first.raise_event({"z": 1}, "actor466")
    second.raise_event({"z": 1}, "actor466")
    assert len(_warned(warnings)) == 2


def test_empty_arg_descriptions_do_not_warn(warnings: list[tuple[Any, ...]]) -> None:
    _make_event(None).raise_event({"z": 1}, "actor466")
    assert _warned(warnings) == []


def test_none_marker_declares_no_keys(warnings: list[tuple[Any, ...]]) -> None:
    event = _make_event({"None": None})
    event.raise_event({}, "actor466")
    assert _warned(warnings) == []
    event.raise_event({"x": 1}, "actor466")
    found = _warned(warnings)
    assert len(found) == 1
    assert found[0][2][2] == "x"


def test_data_list_key_name_is_checked(warnings: list[tuple[Any, ...]]) -> None:
    event = _make_event({"item": "one item"})
    event.raise_event({}, "actor466", data_list=[1], key_name="item")
    assert _warned(warnings) == []
    other = Event("ev_other466", created_by="probe466", arg_descriptions={"a": "first"})
    other.raise_event({}, "actor466", data_list=[1], key_name="item")
    assert _warned(warnings)[0][2][2] == "item"


def test_callback_added_keys_never_warn(warnings: list[tuple[Any, ...]]) -> None:
    event = _make_event({"a": "first"})
    raised = event.raise_event({"a": 1}, "actor466")
    assert raised is not None
    raised.event_data["added_later"] = 1
    assert _warned(warnings) == []


def test_event_data_record_payload_warns(warnings: list[tuple[Any, ...]]) -> None:
    event = _make_event({"a": "first"})
    record = EventDataRecord(owner_id="actor466", event_name="ev_probe466", data={"z": 1})
    event.raise_event(record, "actor466")
    assert _warned(warnings)[0][2][2] == "z"


def test_non_dict_is_rejected_without_undeclared_warning(
    warnings: list[tuple[Any, ...]],
) -> None:
    event = _make_event({"a": "first"})
    assert event.raise_event("nope", "actor466") is None  # type: ignore[arg-type]
    assert _warned(warnings) == []
