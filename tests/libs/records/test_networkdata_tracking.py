"""Tests for NetworkDataLine and NetworkData on pydatatracker (#43)."""

from collections.abc import Callable
from typing import Any
from unittest.mock import MagicMock

import pytest

from bastproxy.libs.records.enums import LineType, Originated
from bastproxy.libs.records.rtypes.clientdata import SendDataDirectlyToClient
from bastproxy.libs.records.rtypes.muddata import SendDataDirectlyToMud
from bastproxy.libs.records.rtypes.networkdata import NetworkData, NetworkDataLine


def test_conversion_and_parents() -> None:
    net_data = NetworkData(["a", b"b"])  # type: ignore[arg-type]
    net_data.append("c")
    net_data.insert(0, "d")
    net_data[1] = "e"
    net_data += ["f"]
    net_data[0:1] = ["g"]
    assert len(net_data) == 5
    for line in net_data:
        assert isinstance(line, NetworkDataLine)
        assert line.parents == [net_data]
        assert line.parent is net_data


def test_appended_line_object_gets_parent() -> None:
    net_data = NetworkData("a")
    line = NetworkDataLine("b")
    assert line.parents == []
    net_data.append(line)
    assert line.parents == [net_data]


def test_bad_item_raises_and_leaves_length() -> None:
    net_data = NetworkData("a")
    with pytest.raises(TypeError):
        net_data.append(5)
    assert len(net_data) == 1


_MUTATORS: dict[str, Callable[[NetworkData], object]] = {
    "append": lambda d: d.append("x"),
    "extend": lambda d: d.extend(["x"]),
    "insert": lambda d: d.insert(0, "x"),
    "__setitem__": lambda d: d.__setitem__(0, "x"),
    "__iadd__": lambda d: d.__iadd__(["x"]),
    "sort": lambda d: d.sort(key=lambda line: str(line.line)),
    "reverse": lambda d: d.reverse(),
    "pop": lambda d: d.pop(),
    "remove": lambda d: d.remove(d[0]),
    "__delitem__": lambda d: d.__delitem__(0),
    "clear": lambda d: d.clear(),
    "__imul__": lambda d: d.__imul__(2),
}


@pytest.mark.parametrize("mutator", list(_MUTATORS))
def test_locked_mutator_raises(mutator: str) -> None:
    net_data = NetworkData(["b", "a"])
    net_data.lock()
    assert net_data.locked
    before = [line.line for line in net_data]
    with pytest.raises(RuntimeError):
        _MUTATORS[mutator](net_data)
    assert [line.line for line in net_data] == before


@pytest.mark.parametrize("mutator", list(_MUTATORS))
def test_unlocked_mutator_records_change_and_keeps_parent(mutator: str) -> None:
    net_data = NetworkData(["b", "a"])
    changes = len(net_data.tracking_changes())
    _MUTATORS[mutator](net_data)
    assert len(net_data.tracking_changes()) > changes
    for line in net_data:
        assert line.parents == [net_data]
        assert line.parent is net_data


def test_locked_line_refuses_but_was_sent_stays_writable() -> None:
    net_data = NetworkData("a")
    net_data.lock()
    line = net_data[0]
    with pytest.raises(RuntimeError):
        line.line = "x"
    with pytest.raises(RuntimeError):
        line.send = False
    line.was_sent = True
    assert line.was_sent


def test_line_lock_is_idempotent_and_original_is_locked() -> None:
    line = NetworkDataLine("a")
    line.lock()
    count = len(line.tracking_changes())
    line.lock()
    assert len(line.tracking_changes()) == count
    with pytest.raises(RuntimeError):
        line.original_line = "x"


def test_format_on_locked_line_is_noop() -> None:
    line = NetworkDataLine("a", originated="client")
    line.lock()
    line.format()
    assert line.line == "a"


def test_line_modified() -> None:
    line = NetworkDataLine("a")
    assert line.line_modified is False
    line.line = "a"
    assert line.line_modified is False
    line.line = "b"
    assert line.line_modified is True


def test_copy_attributes() -> None:
    line = NetworkDataLine(
        "a|b",
        originated="client",
        line_type="IO",
        had_line_endings=False,
        preamble=False,
        prelogin=True,
        color="@r",
    )
    new = NetworkDataLine("a")
    line.copy_attributes(new)
    assert new.line_type == line.line_type
    assert new.originated == "client"
    assert new.original_line == "a|b"
    assert new.preamble is False
    assert new.had_line_endings is False
    assert new.prelogin is True
    assert new.color == "@r"
    assert new.parents == [line]
    assert new.split_from is line


def _fake_api(name: str) -> Callable[..., Any]:
    if name == "plugins.core.clients:client.list":
        return lambda uuid_only=False: []
    if name == "libs.api:api.exists":
        return lambda _n: False
    if name == "plugins.core.proxy:mud.connection.get":
        return lambda: None
    return MagicMock()


@pytest.mark.parametrize("record_cls", [SendDataDirectlyToMud, SendDataDirectlyToClient])
def test_send_formats_then_locks(monkeypatch: pytest.MonkeyPatch, record_cls: type) -> None:
    sent = NetworkDataLine("hello", originated="client")
    hidden = NetworkDataLine("secret", originated="client")
    hidden.send = False
    record = record_cls(NetworkData([sent, hidden]))
    monkeypatch.setattr(record, "api", _fake_api)
    record._exec_()
    assert sent.line == "hello\r\n"
    assert sent._line_locked
    assert hidden._line_locked
    assert record.message.locked
    sent.was_sent = True


@pytest.mark.parametrize(
    ("name", "value"),
    [
        ("originated", Originated.MUD),
        ("line_type", LineType.COMMAND_TELNET),
        ("split_from", "other"),
    ],
)
def test_locked_line_refuses_origin_fields(name: str, value: Any) -> None:
    line = NetworkDataLine("a", originated=Originated.CLIENT)
    line.lock()
    before = getattr(line, name)
    with pytest.raises(RuntimeError):
        setattr(line, name, value)
    assert getattr(line, name) == before


def test_split_from_is_tracked_without_becoming_a_parent() -> None:
    other = NetworkDataLine("other")
    line = NetworkDataLine("a")
    count = len(line.tracking_changes())
    line.split_from = other
    assert len(line.tracking_changes()) == count + 1
    assert line not in other.parents
    assert line.split_from is other
