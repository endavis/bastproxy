"""Tests for the pydatatracker record adapter (#43)."""

from typing import Any

import pytest
from pydatatracker import TrackedList

from bastproxy.libs.api import API
from bastproxy.libs.records.managers.records import RMANAGER
from bastproxy.libs.records.rtypes.networkdata import NetworkData, NetworkDataLine
from bastproxy.libs.records.tracking import (
    MAX_CHANGES,
    TrackedRecordMixin,
    TrackedUpdate,
    tracking_actor,
)


@pytest.fixture
def plugin_apis() -> Any:
    """Stand in for the command args API that format_detailed calls."""
    api = API("test43")
    api.add(
        "plugins.core.commands",
        "command.current.args.get",
        lambda: {},
        description="stand-in",
    )
    try:
        yield
    finally:
        API._class_api.pop("plugins.core.commands:command.current.args.get", None)


def test_equal_content_is_not_equal_identity() -> None:
    a, b = NetworkDataLine("same"), NetworkDataLine("same")
    assert a != b
    assert a == a
    assert hash(a) != hash(b)
    assert len({a, b}) == 2
    na, nb = NetworkData("same"), NetworkData("same")
    assert na != nb
    assert len({na, nb}) == 2
    assert na != list(na)


def test_uuid_registry_and_ordering() -> None:
    first = NetworkDataLine("one")
    second = NetworkDataLine("two")
    assert first.uuid == first._tracking_uuid
    assert RMANAGER.get_record(first.uuid) is first
    assert sorted([second, first]) == [first, second]
    assert isinstance(first, TrackedRecordMixin)


def test_addupdate_appears_in_updates() -> None:
    line = NetworkDataLine("x")
    line.addupdate("Info", "x", extra={"k": 1})
    update = next(u for u in line.updates if u.action == "x")
    assert update.flag == "Info"
    assert update.extra == {"k": "1"}
    assert line.get_update(update.uuid) == update
    assert isinstance(update, TrackedUpdate)


def test_pydatatracker_entries_get_flags() -> None:
    data = NetworkData("a")
    data.lock()
    flags = {u.action: u.flag for u in data.updates}
    assert flags["init"] == "Info"
    assert flags["lock"] == "Info"
    line = NetworkDataLine("a")
    line.line = "b"
    assert [u.flag for u in line.updates if u.action == "update"] == ["Modify", "Modify"]


def test_updates_exclude_rehomed_child_entries() -> None:
    data = NetworkData(["a", "b"])
    data[0].line = "changed"
    own = {u.uuid for u in data.updates}
    child_entries = {u.uuid for u in data[0].updates}
    assert own.isdisjoint(child_entries)
    assert all(len(u.entry.tree) == 1 for u in data.updates)


def test_format_detailed_rows(plugin_apis: None) -> None:
    line = NetworkDataLine("a")
    with tracking_actor("who:what"):
        line.line = "b"
    update = next(u for u in line.updates if u.action == "update")
    rows = update.format_detailed()
    labels = [row.split(":")[0].strip() for row in rows]
    assert labels[:5] == ["UUID", "Record", "Flag", "Actor", "Action"]
    assert any("who:what" in row for row in rows)


def test_actor_attribution() -> None:
    line = NetworkDataLine("a")
    with tracking_actor("x"):
        line.send = False
    entry = line.tracking_changes()[-1]
    assert entry.actor == "x"
    line.is_prompt = True
    assert line.tracking_changes()[-1].actor == ""


def test_formatted_details_list_child_updates_once(plugin_apis: None) -> None:
    api = API("test43b")
    api.add("plugins.core.utils", "dict.key.list", _keys, description="stand-in")
    api.add("plugins.core.utils", "string.dedent", lambda x: x, description="stand-in")
    try:
        data = NetworkData(["a"])
        data[0].line = "changed"
        details = data.get_formatted_details()
    finally:
        API._class_api.pop("plugins.core.utils:dict.key.list", None)
        API._class_api.pop("plugins.core.utils:string.dedent", None)
    uuids = [row.split(":", 1)[1].strip() for row in details if row.strip().startswith("UUID")]
    assert len(uuids) == len(set(uuids))
    assert (
        sum(1 for row in details if row.strip() == "Action          : update") == 2
    )  # line + line_modified


def _keys(d: dict[Any, Any]) -> list[Any]:
    keys: list[Any] = []
    for k, v in d.items():
        keys.append(k)
        keys.extend(_keys(v))
    return keys


def test_max_changes_is_kept() -> None:
    line = NetworkDataLine("a")
    for i in range(MAX_CHANGES + 50):
        line.line = f"v{i}"
    assert len(line.tracking_changes()) == MAX_CHANGES


def test_networkdata_is_a_tracked_list() -> None:
    assert isinstance(NetworkData("a"), TrackedList)
