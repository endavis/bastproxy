"""The result class of the trigger.add API (#426)."""

import dataclasses
from typing import Any

import pytest

from bastproxy.plugins.core.triggers.plugin import _triggers
from bastproxy.plugins.core.triggers.plugin._triggers import TriggerAddResult
from bastproxy.plugins.test.triggers.plugin._triggerex import TriggerExPlugin

from .conftest import Harness


def test_field_order_and_slots() -> None:
    assert [f.name for f in dataclasses.fields(TriggerAddResult)] == ["success", "trigger"]
    assert not hasattr(TriggerAddResult(False, None), "__dict__")


def test_success_returns_the_stored_item(harness: Harness) -> None:
    result = harness.add("ok", r"^a")
    assert isinstance(result, TriggerAddResult)
    assert result.success is True
    assert result.trigger is harness.item("ok")


def test_regexless_add_succeeds(harness: Harness) -> None:
    result = harness.add("plain", None)
    assert result.success is True
    assert result.trigger.original_regex is None


def _dup(harness: Harness) -> Any:
    harness.add("dup", r"^a")
    harness.logged.clear()
    return harness.add("dup", r"^b")


def _bad_regex(harness: Harness) -> Any:
    return harness.add("bad", r"(unclosed")


def _unknown_keyword(harness: Harness) -> Any:
    return harness.add("kw", r"^a", event_name="mine")


def _no_owner(harness: Harness) -> Any:
    harness.api = lambda name: lambda **_kw: None  # type: ignore[method-assign]
    return _triggers.TriggersPlugin._api_trigger_add(harness, "noowner", r"^a", None)


@pytest.mark.parametrize("case", [_dup, _bad_regex, _unknown_keyword, _no_owner])
def test_failures_return_false_none_and_log_once(harness: Harness, case: Any) -> None:
    if case is not _dup:
        harness.logged.clear()
    assert case(harness) == TriggerAddResult(False, None)
    assert len(harness.errors()) == 1


def test_unpacking_raises_type_error(harness: Harness) -> None:
    with pytest.raises(TypeError):
        _success, _trigger = harness.add("u", r"^a")  # pylint: disable=unbalanced-tuple-unpacking


def test_triggerex_registers_on_success(harness: Harness) -> None:
    result = harness.add("test_say", r"^a")
    registered: list[tuple[str, Any]] = []

    class Stub:
        def api(self, name: str) -> Any:
            if name.endswith("trigger.add"):
                return lambda *a, **k: result
            return lambda *a, **k: registered.append(a)

        def _trigger_say(self) -> None:
            pass

    stub = Stub()
    TriggerExPlugin._phook_triggerex_initialize(stub)
    assert registered == [(result.trigger.trigger_id, stub._trigger_say)]
