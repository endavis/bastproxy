"""Tests for on_prompt triggers (#544)."""

# Standard Library
from typing import Any

# Third Party
import pytest

# Project
from bastproxy.libs.records.enums import Originated
from bastproxy.libs.records.rtypes.networkdata import NetworkDataLine

from .conftest import OWNER, Harness


@pytest.fixture(autouse=True)
def _prompt_builtin(harness: Harness) -> None:
    """The real plugin adds the built-in ``prompt`` trigger; the harness does not."""
    harness.add("prompt", None, owner_id="plugins.core.triggers", enabled=False)


def prompt_line(h: Harness, text: str = "<hp>") -> list[str]:
    """Send a MUD line marked as a prompt; return trigger names raised."""
    line = NetworkDataLine(text, originated=Originated.MUD)
    line.is_prompt = True
    h.line = line
    h.current_record = {"line": line}
    before = len(h.raised)
    h._eventcb_check_trigger()
    return [args["trigger_name"] for _event_name, args in h.raised[before:]]


def last_args(h: Harness, name: str) -> dict[str, Any]:
    return next(args for _e, args in reversed(h.raised) if args["trigger_name"] == name)


def test_fires_immediately_before_any_prompt(harness: Harness) -> None:
    harness.add("t", r"^hello", on_prompt=True)
    assert harness.send("hello") == ["t"]
    assert last_args(harness, "t")["prompt"] is None


def test_deferred_until_next_prompt(harness: Harness) -> None:
    harness.add("t", r"^hello", on_prompt=True)
    prompt_line(harness)  # a prompt has been seen
    assert harness.send("hello") == []
    assert len(harness._pending) == 1
    assert prompt_line(harness, "<next>") == ["t"]
    args = last_args(harness, "t")
    assert args["line"].noansi == "hello"
    assert args["prompt"].noansi == "<next>"
    assert not harness._pending


def test_fires_after_the_prompts_own_triggers(harness: Harness) -> None:
    harness.add("held", r"^hello", on_prompt=True)
    harness.add("onprompt_line", r"^<hp>", priority=50)
    prompt_line(harness)
    harness.send("hello")
    assert prompt_line(harness) == ["onprompt_line", "held"]


def test_several_events_fire_in_arrival_order(harness: Harness) -> None:
    harness.add("a", r"^one", on_prompt=True)
    harness.add("b", r"^two", on_prompt=True)
    prompt_line(harness)
    harness.send("two")
    harness.send("one")
    assert prompt_line(harness) == ["b", "a"]


def test_trigger_without_option_fires_immediately(harness: Harness) -> None:
    harness.add("t", r"^hello")
    prompt_line(harness)
    assert harness.send("hello") == ["t"]
    assert "prompt" not in last_args(harness, "t")


def test_on_prompt_trigger_matching_the_prompt_fires_there(harness: Harness) -> None:
    harness.add("t", r"^<hp>", on_prompt=True)
    prompt_line(harness)  # first prompt: none seen before it, fires at once
    before = len(harness.raised)
    prompt_line(harness)
    # matched while a prompt was already seen: queued, then raised by the same line
    assert [a["trigger_name"] for _e, a in harness.raised[before:]] == ["t"]
    assert last_args(harness, "t")["prompt"].noansi == "<hp>"


def test_newline_less_prompt_is_matched_in_one_call(harness: Harness) -> None:
    harness.add("normal", r"^<hp>")
    harness.add("held", r"^<hp>", on_prompt=True)
    assert prompt_line(harness) == ["normal", "held"]


def test_omit_applies_at_match_time_and_hits_at_fire_time(harness: Harness) -> None:
    harness.add("t", r"^hello", on_prompt=True, omit=True)
    prompt_line(harness)
    harness.send("hello")
    assert harness.line.send is False
    assert harness.item("t").hits == 0
    prompt_line(harness)
    assert harness.item("t").hits == 1


def test_stopevaluating_still_works(harness: Harness) -> None:
    harness.add("a", r"^hello", on_prompt=True, stopevaluating=True)
    harness.add("b", r"^hello")
    prompt_line(harness)
    assert harness.send("hello") == []
    assert prompt_line(harness) == ["a"]


def test_failed_when_queues_nothing(harness: Harness) -> None:
    harness.add("t", r"^hello", on_prompt=True, when={"Char.Vitals.hp": ">50"})
    harness.gmcp = {"Char.Vitals.hp": 10}
    prompt_line(harness)
    harness.send("hello")
    assert not harness._pending


def test_removed_trigger_event_is_dropped(harness: Harness) -> None:
    harness.add("t", r"^hello", on_prompt=True)
    prompt_line(harness)
    harness.send("hello")
    harness.api("plugins.core.triggers:trigger.remove")("t", owner_id=OWNER)
    assert prompt_line(harness) == []


def test_disabled_trigger_event_is_dropped(harness: Harness) -> None:
    harness.add("t", r"^hello", on_prompt=True)
    prompt_line(harness)
    harness.send("hello")
    harness.item("t").enabled = False
    assert prompt_line(harness) == []


def test_expired_event_fires_with_no_prompt(harness: Harness) -> None:
    harness.add("t", r"^hello", on_prompt=True)
    prompt_line(harness)
    harness.send("hello")
    harness._pending._max_wait = 0.0
    assert harness.send("other") == ["t"]
    assert last_args(harness, "t")["prompt"] is None
    assert not harness._pending


def test_disconnect_clears_queue_and_state(harness: Harness) -> None:
    harness.add("t", r"^hello", on_prompt=True)
    prompt_line(harness)
    harness.send("hello")
    harness._eventcb_prompts_disconnect()
    assert not harness._pending
    assert harness._prompts_seen is False
    assert harness.send("hello") == ["t"]


def test_builtin_prompt_only_for_prompt_lines(harness: Harness) -> None:
    harness.listen("prompt", "plugins.core.triggers")
    assert harness.send("hello") == []
    assert prompt_line(harness) == ["prompt"]
    assert prompt_line(harness, "") == ["prompt"]


def test_builtin_prompt_needs_a_listener(harness: Harness) -> None:
    assert prompt_line(harness) == []


def test_add_and_update_accept_on_prompt(harness: Harness) -> None:
    result = harness.add("t", r"^x", on_prompt=True)
    assert result.success
    assert harness.item("t").on_prompt is True
    assert harness.add("u", r"^y").trigger.on_prompt is False
    assert harness.api("plugins.core.triggers:trigger.update")("u", {"on_prompt": True})
    assert harness.item("u").on_prompt is True


def test_detail_row_only_when_set(harness: Harness) -> None:
    harness.add("t", r"^x", on_prompt=True)
    harness.add("u", r"^y")
    harness.command_args = {"trigger": [harness.item("t").trigger_id]}
    shown = "\n".join(harness._command_detail().message)
    assert "On Prompt" in shown
    harness.command_args = {"trigger": [harness.item("u").trigger_id]}
    assert "On Prompt" not in "\n".join(harness._command_detail().message)
