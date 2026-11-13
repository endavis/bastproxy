"""Tests for the list and detail commands."""

# Project
from .conftest import OWNER, PLUGIN, Harness


def _list(harness: Harness, match: str = "") -> list[str]:
    harness.command_args = {"match": match}
    result = harness._command_list()
    ok = result.success
    message = result.message
    assert ok is True
    return list(message)


def _detail(harness: Harness, *names: str) -> list[str]:
    harness.command_args = {"trigger": list(names)}
    result = harness._command_detail()
    ok = result.success
    message = result.message
    assert ok is True
    return list(message)


def test_list_has_header_and_all_rows_sorted(harness: Harness) -> None:
    harness.add("zed", r"^z")
    harness.add("abc", r"^a")
    message = _list(harness)
    assert message[0].split()[0] == "Name" and message[0].split()[-1] == "Id"
    assert message[1].startswith("@B---")
    ids = [row.split()[-1] for row in message[2:]]
    assert ids == sorted(harness.triggers)
    assert len(ids) == 5


def test_list_row_shows_name_owner_enabled_hits(harness: Harness) -> None:
    harness.add("abc", r"^a")
    harness.send("a")
    row = next(r for r in _list(harness) if r.endswith("t_plugins.test.owner_abc"))
    assert row.split() == ["abc", ":", OWNER, "True", "1", "t_plugins.test.owner_abc"]


def test_list_match_filters_by_id_substring(harness: Harness) -> None:
    harness.add("abc", r"^a")
    harness.add("xyz", r"^x")
    rows = _list(harness, "xyz")[2:]
    assert len(rows) == 1
    assert rows[0].endswith("t_plugins.test.owner_xyz")


def test_list_match_filters_by_owner_id(harness: Harness) -> None:
    harness.add("abc", r"^a")
    harness.add("other", r"^o", owner_id="plugins.test.other")
    rows = _list(harness, "plugins.test.other")[2:]
    assert len(rows) == 1
    assert rows[0].startswith("other")


def test_list_match_nothing_gives_only_header(harness: Harness) -> None:
    assert len(_list(harness, "nomatchatall")) == 2


def test_detail_without_args_asks_for_a_name(harness: Harness) -> None:
    assert _detail(harness) == ["Please provide a trigger name"]


def test_detail_unknown_trigger(harness: Harness) -> None:
    assert _detail(harness, "nope") == ["trigger nope does not exist"]


def test_detail_known_trigger_rows_without_functions(harness: Harness) -> None:
    harness.add("abc", r"^a", group="g1", priority=3, omit=True)
    message = _detail(harness, "t_plugins.test.owner_abc")
    joined = "\n".join(message)
    assert "Name" in message[0]
    assert message[0].endswith(": abc")
    assert any(r.startswith("Defined in") and r.endswith(OWNER) for r in message)
    assert any(r.startswith("Group") and r.endswith("g1") for r in message)
    assert any(r.startswith("Priority") and r.endswith("3") for r in message)
    assert any(r.startswith("Omit") and r.endswith("True") for r in message)
    assert not any(r.startswith("Argument Types") for r in message)
    assert "Event Details:" not in joined
    assert message[-1] == "No functions registered for this trigger"


def test_detail_shows_argument_types(harness: Harness) -> None:
    harness.add("abc", r"^hp (?P<hp>\d+)", argtypes={"hp": int})
    message = _detail(harness, "t_plugins.test.owner_abc")
    row = next(r for r in message if r.startswith("Argument Types"))
    assert "hp" in row
    assert "int" in row


def test_detail_with_event_shows_event_details(harness: Harness) -> None:
    harness.add("abc", r"^a")
    event_name = harness.item("abc").event_name
    harness.existing_events.add(event_name)
    harness.event_details[event_name] = ["detail line 1", "detail line 2"]
    message = _detail(harness, "t_plugins.test.owner_abc")
    assert message[-4:] == ["", "Event Details:", "detail line 1", "detail line 2"]
    assert "No functions registered for this trigger" not in message


def test_detail_handles_several_triggers(harness: Harness) -> None:
    harness.add("abc", r"^a")
    message = _detail(harness, "t_plugins.test.owner_abc", "missing")
    assert message[-1] == "trigger missing does not exist"
    assert message[0].endswith(": abc")


def test_detail_builtin_has_no_regex(harness: Harness) -> None:
    message = _detail(harness, harness.create_trigger_id("all", PLUGIN))
    assert any(r.startswith("Regex") and r.endswith("None") for r in message)
