"""Regression tests for #252: TriggerItem.hits counts every raise."""

# Standard Library
from types import SimpleNamespace
from typing import Any

# Project
from bastproxy.plugins.core.triggers.plugin._triggers import TriggerItem


def _item() -> TriggerItem:
    item = TriggerItem(
        "plugins.test252",
        "trig",
        "^abc$",
        "regex_id",
        "^abc$",
        trigger_id="plugins.test252_trig",
    )

    def raise_stub(_event_name: str, event_args: dict[str, Any]) -> dict[str, Any]:
        return event_args

    item.api = lambda _name: raise_stub  # type: ignore[assignment]
    return item


def test_hits_start_at_zero() -> None:
    assert _item().hits == 0


def test_every_raise_counts_as_a_hit() -> None:
    item = _item()
    line = SimpleNamespace(sendtoclients=True)
    item.raisetrigger({"line": line})
    item.raisetrigger({"line": line})
    assert item.hits == 2
