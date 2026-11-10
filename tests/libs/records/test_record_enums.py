"""Tests for the record enums and the isinstance parent check (#237)."""

import re
from collections.abc import Iterator
from typing import Any

import pytest

from bastproxy.libs.api import API
from bastproxy.libs.records import LineType, Originated, UpdateFlag
from bastproxy.libs.records.managers.records import RMANAGER
from bastproxy.libs.records.rtypes.base import BaseRecord
from bastproxy.libs.records.rtypes.networkdata import NetworkData, NetworkDataLine


@pytest.fixture(autouse=True)
def _restore_manager(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    monkeypatch.setattr(RMANAGER, "capture_stacks", False)
    monkeypatch.setattr(RMANAGER, "max_changes", RMANAGER.max_changes)
    yield


@pytest.fixture(autouse=True)
def _plugin_apis() -> Iterator[None]:
    """Give the class-wide API the one plugin API the detail view calls, then remove it."""
    api = API("test237")
    stand_ins: dict[str, Any] = {
        "plugins.core.utils:dict.key.list": lambda d: list(d),
        "plugins.core.utils:string.dedent": lambda x: x,
        "plugins.core.commands:command.current.args.get": lambda: {},
    }
    for location, func in stand_ins.items():
        package, name = location.split(":")
        api.add(package, name, func, description="stand-in")
    yield
    for location in stand_ins:
        API._class_api.pop(location, None)


class _Data(NetworkData):
    """A NetworkData subclass."""


class _Line(NetworkDataLine):
    """A NetworkDataLine subclass."""


def test_members_equal_their_old_strings() -> None:
    expected = {
        Originated.MUD: "mud",
        Originated.CLIENT: "client",
        Originated.INTERNAL: "internal",
        LineType.IO: "IO",
        LineType.COMMAND_TELNET: "COMMAND-TELNET",
        UpdateFlag.MODIFY: "Modify",
        UpdateFlag.SET_FLAG: "Set Flag",
        UpdateFlag.INFO: "Info",
    }
    assert len(expected) == 8
    for member, value in expected.items():
        assert member == value
        assert str(member) == value


def _count_adds(monkeypatch: pytest.MonkeyPatch) -> list[Any]:
    added: list[Any] = []
    original = RMANAGER.add

    def spy(record: Any) -> Any:
        added.append(record)
        return original(record)

    monkeypatch.setattr(RMANAGER, "add", spy)
    return added


@pytest.mark.parametrize(
    "kwargs", [{"originated": "clients"}, {"line_type": "TELNET"}], ids=["originated", "line_type"]
)
def test_unknown_value_raises_and_registers_nothing(
    monkeypatch: pytest.MonkeyPatch, kwargs: dict[str, str]
) -> None:
    added = _count_adds(monkeypatch)
    with pytest.raises(ValueError):
        NetworkDataLine("x", **kwargs)  # type: ignore[arg-type]
    assert added == []


def test_valid_string_is_coerced_to_the_member() -> None:
    line = NetworkDataLine("x", originated="mud", line_type="COMMAND-TELNET")
    assert line.originated is Originated.MUD
    assert line.line_type is LineType.COMMAND_TELNET


@pytest.mark.parametrize("as_enum", [True, False])
def test_shortcut_properties_for_every_member(as_enum: bool) -> None:
    for originated in Originated:
        line = NetworkDataLine("x", originated=originated if as_enum else originated.value)
        assert line.internal is (originated is Originated.INTERNAL)
        assert line.fromclient is (originated is Originated.CLIENT)
        assert line.frommud is (originated is Originated.MUD)
    for line_type in LineType:
        line = NetworkDataLine("x", line_type=line_type if as_enum else line_type.value)
        assert line.is_io is (line_type is LineType.IO)
        assert line.is_command_telnet is (line_type is LineType.COMMAND_TELNET)


def test_display_is_unchanged() -> None:
    line = NetworkDataLine("x", originated=Originated.MUD)
    assert " mud " in line.one_line_summary()
    details = "\n".join(line.get_formatted_details())
    assert "mud" in details
    assert "IO" in details


def test_unknown_flag_raises_on_a_base_record() -> None:
    record = BaseRecord()
    with pytest.raises(ValueError):
        record.addupdate("Bogus", "x")
    assert record.updates == []


def test_unknown_flag_raises_on_a_network_data_line() -> None:
    line = NetworkDataLine("x")
    before = len(line.updates)
    with pytest.raises(ValueError):
        line.addupdate("Bogus", "x")
    assert len(line.updates) == before


@pytest.mark.parametrize("flag", [UpdateFlag.SET_FLAG, "Set Flag"])
def test_set_flag_as_enum_or_string(flag: Any) -> None:
    record = BaseRecord()
    record.addupdate(flag, "set")
    update = record.updates[-1]
    assert update.flag == "Set Flag"
    assert any("Set Flag" in row for row in update.format_detailed())


def test_flags_pydatatracker_leaves_out_are_worked_out() -> None:
    line = NetworkDataLine("x")
    line.line = "changed"
    line.lock()
    flags = [(update.action, update.flag) for update in line.updates]
    assert ("update", "Modify") in flags
    assert any(action in ("init", "lock") and flag == "Info" for action, flag in flags)


def test_add_parent_accepts_subclasses() -> None:
    line = NetworkDataLine("x")
    data = _Data()
    parent_line = _Line("p")
    line.add_parent(data)
    line.add_parent(parent_line, reset=False)
    assert data in line.parents
    assert parent_line in line.parents


def test_line_stored_in_a_subclass_gets_it_as_parent() -> None:
    data = _Data()
    data.append(NetworkDataLine("x"))
    assert data in data[0].parents


def test_add_parent_ignores_other_parents() -> None:
    line = NetworkDataLine("x")
    line.add_parent(BaseRecord())
    line.add_parent(object())
    assert line.parents == []


def test_detail_view_lists_origin_and_type_once() -> None:
    line = NetworkDataLine("a", originated=Originated.MUD)
    details = "\n".join(line.get_formatted_details())
    assert details.count("Originated") == 1
    assert len(re.findall(r"Type\s*:\s*IO", details)) == 1
    for name in ("originated", "line_type", "split_from"):
        assert name not in details
