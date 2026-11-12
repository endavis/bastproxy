"""Tests for trigger.remove.for.owner cleanup and the built-in triggers."""

# Standard Library
import logging
from typing import Any

# Third Party
import pytest

# Project
from bastproxy.plugins.core.triggers.plugin._triggers import TriggersPlugin

from .conftest import OWNER, PLUGIN, Harness

OTHER = "plugins.test.other"


def test_remove_for_owner_removes_all_kinds(harness: Harness) -> None:
    harness.add("noregex", None)
    harness.add("withregex", r"^hello")
    harness.add("listened", r"^bye")
    harness.listen("listened")
    harness.add("theirs", r"^x", owner_id=OTHER)
    harness.add("theirs_noregex", None, owner_id=OTHER)

    harness.api("plugins.core.triggers:trigger.remove.for.owner")(OWNER)

    assert not [i for i in harness.triggers.values() if i.owner_id == OWNER]
    assert "noregex" not in harness.ordered_names()
    assert "withregex" not in harness.ordered_names()
    assert "listened" not in harness.ordered_names()
    assert harness.item("theirs", OTHER)
    assert harness.item("theirs_noregex", OTHER)
    assert "theirs" in harness.ordered_names()


def test_failing_removal_does_not_stop_the_rest(
    harness: Harness, monkeypatch: pytest.MonkeyPatch
) -> None:
    harness.add("first", r"^a")
    harness.add("bad", r"^b")
    harness.add("last", None)
    real = TriggersPlugin._sync_order_remove

    def flaky(item: Any) -> None:
        if item.trigger_name == "bad":
            raise RuntimeError("boom")
        real(harness, item)  # type: ignore[arg-type]

    monkeypatch.setattr(harness, "_sync_order_remove", flaky)

    harness.api("plugins.core.triggers:trigger.remove.for.owner")(OWNER)

    remaining = [i.trigger_name for i in harness.triggers.values() if i.owner_id == OWNER]
    assert remaining == ["bad"]
    errors = harness.errors()
    assert len(errors) == 1
    assert errors[0][1] == logging.ERROR
    assert "bad" in errors[0]


def test_readd_regexless_trigger_after_remove_for_owner(harness: Harness) -> None:
    harness.add("noregex", None)
    harness.api("plugins.core.triggers:trigger.remove.for.owner")(OWNER)
    assert harness.api("plugins.core.triggers:trigger.get")("noregex", OWNER) is None

    harness.add("noregex", None)

    assert harness.item("noregex").trigger_name == "noregex"


def test_initialize_adds_builtins_enabled(
    harness: Harness, monkeypatch: pytest.MonkeyPatch
) -> None:
    harness.triggers.clear()
    harness._ordered.clear()
    original = harness.api

    def api(name: str) -> Any:
        if name == "plugins.core.settings:setting.add":
            return lambda *a, **k: None
        return original(name)

    monkeypatch.setattr(harness, "api", api)

    TriggersPlugin._phook_initialize(harness)

    for name in ("beall", "all", "emptyline"):
        assert harness.item(name, PLUGIN).enabled is True
