"""Regression tests for #467: plugin.state.save raises the declared ev_<id>_savestate event."""

from collections.abc import Callable, Iterator
from typing import Any
from unittest.mock import MagicMock

import pytest

from bastproxy.libs.api import API
from bastproxy.plugins._baseplugin import BasePlugin
from bastproxy.plugins.core.events.libs.process import _raisedevent
from bastproxy.plugins.core.events.plugin._event import Event

RAISE_API = "plugins.core.events:event.raise"
ADD_API = "plugins.core.events:event.add"
PLUGIN_ID = "plugins.test.stub"


class _Stub(BasePlugin):
    """A BasePlugin that skips __init__ and the plugin hooks."""

    def __init__(self, apis: dict[str, Callable[..., Any]]) -> None:
        self.plugin_id = PLUGIN_ID
        self.api = MagicMock(side_effect=lambda name: apis.get(name, MagicMock()))

    def _process_plugin_hook(self, plugin_hook: str, **kwargs: Any) -> dict[str, Any]:
        return {}


def _declared_and_raised() -> tuple[list[str], list[tuple[str, Any]]]:
    declared: list[str] = []
    raised: list[tuple[str, Any]] = []

    def add(name: str, *_a: Any, **_k: Any) -> None:
        declared.append(name)

    def raise_event(name: str, event_args: Any = None, **_k: Any) -> None:
        raised.append((name, event_args))

    stub: Any = _Stub({ADD_API: add, RAISE_API: raise_event})
    stub._phook_base_initialize()
    stub._api_plugin_state_save()
    return declared, raised


def test_state_save_raises_the_declared_savestate_event() -> None:
    declared, raised = _declared_and_raised()
    assert f"ev_{PLUGIN_ID}_savestate" in declared
    assert raised[0][0] == f"ev_{PLUGIN_ID}_savestate"
    assert raised[0][0] in declared


def test_state_save_still_raises_plugin_save() -> None:
    _, raised = _declared_and_raised()
    assert ("ev_plugin_save", {"plugin_id": PLUGIN_ID}) in raised


@pytest.fixture
def log_setting() -> Iterator[dict[str, bool]]:
    state = {"value": False}
    api = API("test467")
    api.add(
        "plugins.core.settings",
        "setting.get",
        lambda *_a, **_k: state["value"],
        description="stand-in",
    )
    try:
        yield state
    finally:
        API._class_api.pop("plugins.core.settings:setting.get", None)


def _raise_and_count_logs(monkeypatch: pytest.MonkeyPatch, name: str) -> int:
    log_mock = MagicMock()
    monkeypatch.setattr(_raisedevent, "log_to", log_mock)
    Event(name, created_by="test467").raise_event({}, "test467")
    return int(log_mock.call_count)


def test_savestate_event_not_logged_when_log_savestate_false(
    monkeypatch: pytest.MonkeyPatch, log_setting: dict[str, bool]
) -> None:
    log_setting["value"] = False
    assert _raise_and_count_logs(monkeypatch, f"ev_{PLUGIN_ID}_savestate") == 0


def test_savestate_event_logged_when_log_savestate_true(
    monkeypatch: pytest.MonkeyPatch, log_setting: dict[str, bool]
) -> None:
    log_setting["value"] = True
    assert _raise_and_count_logs(monkeypatch, f"ev_{PLUGIN_ID}_savestate") == 1
