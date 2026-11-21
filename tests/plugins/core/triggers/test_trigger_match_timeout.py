"""A match that runs out of time counts as no match (#697)."""

# Standard Library
import asyncio
import logging
from types import SimpleNamespace
from typing import Any

# Third Party
import pytest
import regex as re

# Project
from bastproxy.plugins.core.triggers.plugin import _waiters
from bastproxy.plugins.core.triggers.plugin._waiters import MATCH_TIMEOUT, WaiterRegistry

from .conftest import Harness


class TimingOutPattern:
    """Stands in for a compiled pattern whose match always runs out of time."""

    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

    def match(self, text: str, **kwargs: Any) -> None:
        self.calls.append(kwargs)
        raise TimeoutError


def warnings(harness: Harness) -> list[tuple[Any, ...]]:
    return [c for c in harness.logged if len(c) > 1 and c[1] == logging.WARNING]


def test_timeout_is_passed_to_the_match(harness: Harness) -> None:
    harness.add("real", r"^go")
    item = harness.item("real")
    seen: list[dict[str, Any]] = []
    original = item.original_regex_compiled

    class Spy:
        def match(self, text: str, **kwargs: Any) -> Any:
            seen.append(kwargs)
            return original.match(text, **kwargs)

    item.original_regex_compiled = Spy()
    assert harness.send("go") == ["real"]
    assert seen == [{"timeout": MATCH_TIMEOUT}]


def test_timed_out_match_counts_as_no_match(harness: Harness) -> None:
    harness.add("slow", r"^go")
    harness.item("slow").original_regex_compiled = TimingOutPattern()
    assert harness.send("go") == []
    assert harness.errors() == []


def test_later_triggers_still_match_the_line(harness: Harness) -> None:
    harness.add("slow", r"^go", priority=1)
    harness.add("after", r"^go", priority=2)
    harness.item("slow").original_regex_compiled = TimingOutPattern()
    assert harness.send("go") == ["after"]


def test_warning_is_logged_once_and_names_the_trigger(harness: Harness) -> None:
    harness.add("slow", r"^go")
    harness.item("slow").original_regex_compiled = TimingOutPattern()
    harness.send("go")
    harness.send("go")
    found = warnings(harness)
    assert len(found) == 1
    assert harness.item("slow").trigger_id in found[0]


def test_update_lets_the_warning_be_logged_again(harness: Harness) -> None:
    harness.add("slow", r"^go")
    harness.item("slow").original_regex_compiled = TimingOutPattern()
    harness.send("go")
    harness._api_trigger_update("slow", {"priority": 5})
    harness.send("go")
    assert len(warnings(harness)) == 2


def test_re_added_trigger_warns_again(harness: Harness) -> None:
    harness.add("slow", r"^go")
    harness.item("slow").original_regex_compiled = TimingOutPattern()
    harness.send("go")
    harness._api_trigger_remove("slow")
    harness.add("slow", r"^go")
    harness.item("slow").original_regex_compiled = TimingOutPattern()
    harness.send("go")
    assert len(warnings(harness)) == 2


def test_shared_pattern_timeout_is_matched_once_and_cached(harness: Harness) -> None:
    harness.add("one", r"^go")
    harness.add("two", r"^go")
    harness.add("after", r"^g")
    one, two = harness.item("one"), harness.item("two")
    assert one.shared_pattern
    pattern = TimingOutPattern()
    one.original_regex_compiled = pattern
    two.original_regex_compiled = pattern
    assert harness.send("go") == ["after"]
    assert len(pattern.calls) == 1


async def test_waiter_whose_match_times_out_keeps_waiting(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    logged: list[tuple[Any, ...]] = []
    monkeypatch.setattr(_waiters, "log_to", lambda *a, **k: logged.append(a))
    slow = TimingOutPattern()
    monkeypatch.setattr(_waiters, "re", SimpleNamespace(compile=lambda _p: slow, error=re.error))
    registry = WaiterRegistry(lambda _c, _o: None)
    waiter = registry.add("owner")
    task = asyncio.create_task(waiter.wait_for(r"^go", 0.2))
    await asyncio.sleep(0)
    registry.feed("go", False)
    registry.feed("go", False)
    assert await task is None
    assert slow.calls == [{"timeout": MATCH_TIMEOUT}] * 2
    assert len([c for c in logged if c[1] == logging.WARNING]) == 1
    assert "owner" in logged[0]
