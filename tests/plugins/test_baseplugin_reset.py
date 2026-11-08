"""Regression tests for BasePlugin._api_plugin_reset (#176)."""

from collections.abc import Callable
from types import SimpleNamespace
from typing import Any
from unittest.mock import MagicMock

from bastproxy.plugins._baseplugin import BasePlugin

RAISE_API = "plugins.core.events:raise.event"


class _Stub(BasePlugin):
    """A BasePlugin that skips __init__."""

    def __init__(self, apis: dict[str, Callable[..., Any]]) -> None:
        self.plugin_id = "plugins.test.stub"
        self.api = MagicMock(side_effect=lambda name: apis.get(name, MagicMock()))


def test_reset_returns_plugins_that_acted() -> None:
    def raise_event(name: str, event_args: dict[str, Any]) -> SimpleNamespace:
        assert name == "ev_plugin_reset"
        assert event_args["plugin_id"] == "plugins.test.stub"
        event_args["plugins_that_acted"].append("plugins.core.settings")
        return SimpleNamespace(event_data=event_args)

    stub: Any = _Stub({RAISE_API: raise_event})
    assert stub._api_plugin_reset() == ["plugins.core.settings"]


def test_reset_with_no_event_result_returns_empty_list() -> None:
    stub: Any = _Stub({RAISE_API: lambda *_a, **_k: None})
    assert stub._api_plugin_reset() == []
