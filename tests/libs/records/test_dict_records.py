"""Tests for dict records on pydatatracker TrackedDict (#246, #43 slice 2)."""

from collections.abc import Callable, Iterator
from typing import Any

import pytest
from pydatatracker import TrackedDict

from bastproxy.libs.api import API
from bastproxy.libs.records.managers.records import RMANAGER
from bastproxy.libs.records.rtypes.dictrecord import BaseDictRecord
from bastproxy.libs.records.rtypes.networkdata import NetworkData, NetworkDataLine
from bastproxy.plugins.core.commands.libs.data.cmdargs import CmdArgsRecord
from bastproxy.plugins.core.events.libs.data._event import EventDataRecord


@pytest.fixture
def plugin_apis() -> Iterator[None]:
    """Stand in for the command args API that format_detailed calls."""
    stand_ins: dict[str, Callable[..., Any]] = {
        "plugins.core.commands:command.current.args.get": lambda: {},
        "plugins.core.utils:dict.key.list": lambda d: list(d),
        "plugins.core.utils:string.dedent": lambda lines: lines,
    }
    api = API("test246")
    for full_name, func in stand_ins.items():
        top, name = full_name.split(":")
        api.add(top, name, func, description="stand-in")
    try:
        yield
    finally:
        for full_name in stand_ins:
            API._class_api.pop(full_name, None)


def test_identity() -> None:
    data = {"k": "v"}
    a = BaseDictRecord(data=data)
    b = BaseDictRecord(data={"k": "v"})
    assert a == a
    assert a != b
    assert hash(a) != hash(b)
    assert len({a, b}) == 2
    assert a != {"k": "v"}
    assert isinstance(a, dict)
    assert RMANAGER.get_record(a.uuid) is a
    assert a.original_data == data


def test_non_dict_raises() -> None:
    with pytest.raises(TypeError):
        BaseDictRecord(data=["x"])  # type: ignore[arg-type]


def test_track_record_is_ignored() -> None:
    rec = BaseDictRecord(data={"k": "v"}, track_record=False)
    assert rec["k"] == "v"


_MUTATORS: dict[str, Callable[[BaseDictRecord], Any]] = {
    "set": lambda r: r.__setitem__("a", 2),
    "del": lambda r: r.__delitem__("a"),
    "pop": lambda r: r.pop("a"),
    "pop_default": lambda r: r.pop("zz", None),
    "popitem": lambda r: r.popitem(),
    "update": lambda r: r.update({"b": 1}),
    "clear": lambda r: r.clear(),
    "setdefault": lambda r: r.setdefault("a", 5),
    "setdefault_new": lambda r: r.setdefault("n", 5),
    "ior": lambda r: r.__ior__({"b": 1}),
}


@pytest.mark.parametrize(
    "name", ["set", "del", "pop", "popitem", "update", "clear", "setdefault_new"]
)
def test_mutation_adds_modify_update(name: str) -> None:
    rec = BaseDictRecord(data={"a": 1})
    before = len(rec.updates)
    _MUTATORS[name](rec)
    new = rec.updates[before:]
    assert new
    assert all(u.flag == "Modify" for u in new)


def test_addupdate_savedata_false() -> None:
    rec = BaseDictRecord(data={"a": 1})
    rec.addupdate("Info", "something", extra={"k": 1}, savedata=False)
    update = next(u for u in rec.updates if u.action == "something")
    assert str(update.extra["k"]) == "1"


@pytest.mark.parametrize("name", list(_MUTATORS))
def test_locked_writes_raise(name: str) -> None:
    rec = BaseDictRecord(data={"a": 1})
    rec.lock()
    assert rec.locked
    with pytest.raises(RuntimeError):
        _MUTATORS[name](rec)
    assert dict(rec) == {"a": 1}


def test_locked_reads_work() -> None:
    rec = BaseDictRecord(data={"a": 1})
    rec.lock()
    assert rec.get("a") == 1
    assert "a" in rec
    assert list(rec) == ["a"]
    copied = rec.copy()
    assert type(copied) is dict
    assert copied == {"a": 1}


def test_locked_record_value_stays_locked_in_unlocked_record() -> None:
    net_data = NetworkData("x")
    net_data.lock()
    rec = BaseDictRecord(data={})
    rec["net_data"] = net_data
    assert net_data.locked
    assert not rec.locked


def test_locking_record_does_not_lock_stored_line() -> None:
    line = NetworkDataLine("x")
    rec = BaseDictRecord(data={})
    rec["line"] = line
    rec.lock()
    line.line = "changed"
    line.was_sent = True
    assert line.line == "changed"


def test_replace_and_pop_stored_line() -> None:
    rec = BaseDictRecord(data={})
    rec["line"] = NetworkDataLine("one")
    rec["line"] = NetworkDataLine("two")
    assert rec["line"].line == "two"
    assert rec.pop("line").line == "two"
    assert "line" not in rec


def test_nested_tracked_dict_is_locked_by_cascade() -> None:
    inner = TrackedDict({"x": 1})
    rec = BaseDictRecord(data={})
    rec["inner"] = inner
    rec.lock()
    with pytest.raises(RuntimeError):
        inner["x"] = 2


@pytest.mark.usefixtures("plugin_apis")
def test_display_event_data_record() -> None:
    rec = EventDataRecord(event_name="ev_test246", data={"a": "1"})
    rec["b"] = "2"
    text = "\n".join(rec.get_formatted_details())
    assert "Data" in text
    assert "Original Data" in text
    assert "Event Name" in text
    assert "ev_test246" in text
    assert "ev_test246" in rec.one_line_summary()


@pytest.mark.usefixtures("plugin_apis")
def test_display_cmdargs_record() -> None:
    rec = CmdArgsRecord(data={"a": "1"}, arg_string="foo", command="cmd246")
    text = "\n".join(rec.get_formatted_details())
    assert "Command" in text
    assert "cmd246" in text
    assert "cmd246" in rec.one_line_summary()


def test_base_one_line_summary() -> None:
    rec = BaseDictRecord(data={"k": " v "})
    assert rec.one_line_summary().endswith("v")
    assert BaseDictRecord().one_line_summary().startswith("BaseDictRecord")


def test_cmdargs_record() -> None:
    rec = CmdArgsRecord(data={"help": False, "items": ["a"]}, command="x")
    assert rec["help"] is False
    assert rec["items"] == ["a"]
    assert isinstance(rec["items"], list)
