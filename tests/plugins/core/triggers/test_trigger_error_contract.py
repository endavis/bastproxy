"""Tests for the trigger APIs' error contract: log at ERROR, return a falsy value, never raise."""

# Standard Library
import importlib.util
import inspect
import logging
import re
import sys
from pathlib import Path
from typing import Any

# Third Party
import pytest

# Project
from bastproxy.plugins.core.triggers.plugin import _triggers
from bastproxy.plugins.core.triggers.plugin._triggers import TriggerItem
from bastproxy.plugins.test.triggers.plugin._triggerex import TriggerExPlugin

from .conftest import OWNER, Harness

API = "plugins.core.triggers:"


def test_add_duplicate_returns_false_and_logs(harness: Harness) -> None:
    assert harness.add("dup", r"^a")
    harness.logged.clear()
    assert harness.add("dup", r"^b") == (False, None)
    assert len(harness.errors()) == 1


def test_add_bad_regex_returns_false_none_and_logs(harness: Harness) -> None:
    harness.logged.clear()
    success, trigger = harness.add("bad", r"(unclosed")
    assert (success, trigger) == (False, None)
    assert len(harness.errors()) == 1


def test_add_without_owner_logs_and_does_not_print(
    harness: Harness, capsys: pytest.CaptureFixture[str]
) -> None:
    harness.api = lambda name: lambda **_kw: None  # type: ignore[method-assign]
    harness.logged.clear()
    result = _triggers.TriggersPlugin._api_trigger_add(harness, "noowner", r"^a", None)
    assert result == (False, None)
    assert len(harness.errors()) == 1
    assert capsys.readouterr().out == ""


def test_add_unknown_keyword_returns_false_and_logs(harness: Harness) -> None:
    harness.logged.clear()
    assert harness.add("kw", r"^a", event_name="mine") == (False, None)
    assert len(harness.errors()) == 1
    assert harness.create_trigger_id("kw", OWNER) not in harness.triggers


def test_add_success_returns_tuple(harness: Harness) -> None:
    ok, item = harness.add("good", r"^a")
    assert ok is True
    assert item.trigger_name == "good"


def test_trigger_item_has_no_event_name_parameter() -> None:
    assert "event_name" not in inspect.signature(TriggerItem.__init__).parameters


def test_get_unknown_returns_none_without_logging(harness: Harness) -> None:
    harness.logged.clear()
    assert harness.api(API + "trigger.get")("missing") is None
    assert harness.logged == []


@pytest.mark.parametrize(
    "call",
    [
        lambda h: h.api(API + "trigger.update")("missing", {"omit": True}),
        lambda h: h.api(API + "trigger.remove")("missing"),
        lambda h: h.api(API + "trigger.register")("missing", lambda: None),
        lambda h: h.api(API + "trigger.unregister")("missing", lambda: None),
        lambda h: h.api(API + "trigger.toggle.enable")("missing", True),
        lambda h: h.api(API + "trigger.toggle.omit")("missing", True),
        lambda h: h.api(API + "group.toggle.enable")("missing_group", True),
    ],
)
def test_unknown_target_returns_false_and_logs(harness: Harness, call: Any) -> None:
    harness.logged.clear()
    assert call(harness) is False
    assert len(harness.errors()) == 1


def test_register_and_unregister_known_trigger_return_true(harness: Harness) -> None:
    harness.add("known", r"^a")
    calls: list[tuple[str, str]] = []
    harness.api = _wrap_events(harness, calls)  # type: ignore[method-assign]
    assert harness.api(API + "trigger.register")("known", lambda: None) is True
    assert harness.api(API + "trigger.unregister")("known", lambda: None) is True
    assert [c[0] for c in calls] == ["register", "unregister"]
    event_name = harness.item("known").event_name
    assert all(c[1] == event_name for c in calls)


def _wrap_events(harness: Harness, calls: list[tuple[str, str]]) -> Any:
    original = harness.api

    def api(name: str) -> Any:
        if name == "plugins.core.events:event.register":
            return lambda event_name, _func, **_kw: calls.append(("register", event_name))
        if name == "plugins.core.events:event.unregister":
            return lambda event_name, _func: calls.append(("unregister", event_name))
        return original(name)

    return api


def test_toggles_known_trigger_return_true(harness: Harness) -> None:
    harness.add("tog", r"^a", group="g")
    assert harness.api(API + "trigger.toggle.enable")("tog", False) is True
    assert harness.api(API + "trigger.toggle.omit")("tog", True) is True
    assert harness.api(API + "group.toggle.enable")("g", True) is True
    assert harness.item("tog").enabled is True


def test_remove_for_owner_true_when_all_removed(harness: Harness) -> None:
    harness.add("one", r"^a")
    assert harness.api(API + "trigger.remove.for.owner")(OWNER) is True


def test_remove_for_owner_false_when_a_removal_fails(
    harness: Harness, monkeypatch: pytest.MonkeyPatch
) -> None:
    harness.add("one", r"^a")
    harness.add("two", r"^b")
    real = _triggers.TriggersPlugin._sync_order_remove

    def flaky(item: Any) -> None:
        if item.trigger_name == "one":
            raise RuntimeError("boom")
        real(harness, item)  # type: ignore[arg-type]

    monkeypatch.setattr(harness, "_sync_order_remove", flaky)
    assert harness.api(API + "trigger.remove.for.owner")(OWNER) is False
    assert any(call[1] == logging.ERROR for call in harness.logged if len(call) > 1)
    assert harness.create_trigger_id("two", OWNER) not in harness.triggers


def test_remove_for_owner_false_when_trigger_refuses(harness: Harness) -> None:
    harness.add("one", r"^a")
    harness.api = _failing_remove(harness)  # type: ignore[method-assign]
    assert harness.api(API + "trigger.remove.for.owner")(OWNER) is False


def _failing_remove(harness: Harness) -> Any:
    original = harness.api

    def api(name: str) -> Any:
        if name == API + "trigger.remove":
            return lambda *a, **k: False
        return original(name)

    return api


def test_missing_regex_raises_import_error_not_system_exit(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = Path(_triggers.__file__)
    spec = importlib.util.spec_from_file_location("_triggers_no_regex", source)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    monkeypatch.setitem(sys.modules, "regex", None)
    with pytest.raises(ImportError):
        spec.loader.exec_module(module)


def test_no_print_or_sys_exit_in_triggers_package() -> None:
    package = Path(_triggers.__file__).parent
    for path in package.glob("*.py"):
        text = path.read_text()
        assert not re.search(r"\bprint\(", text), path
        assert "sys.exit" not in text, path


def test_triggerex_handles_failed_add() -> None:
    calls: list[str] = []

    class Stub:
        def api(self, name: str) -> Any:
            calls.append(name)
            return lambda *a, **k: (False, None)

        _trigger_say = None

    TriggerExPlugin._phook_triggerex_initialize(Stub())
    assert calls == [API + "trigger.add"]
