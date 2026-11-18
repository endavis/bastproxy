"""Tests for the proxy's reaction to the mud disconnect event (#559)."""

from typing import Any
from unittest.mock import MagicMock

import pytest

from bastproxy.libs.net.mud import MUD_DISCONNECT_EVENT, MUD_DISCONNECT_EVENT_SPEC
from bastproxy.plugins.core.proxy.plugin._proxy import ProxyPlugin


def _stub(active: bool) -> tuple[MagicMock, list[bool]]:
    stub = MagicMock()
    stub.plugin_id = "plugins.core.proxy"
    sets: list[bool] = []

    def api(name: str) -> Any:
        if name == "libs.api:character.is.active":
            return lambda: active
        if name == "libs.api:character.active.set":
            return lambda value: sets.append(value)
        return MagicMock()

    stub.api.side_effect = api
    return stub, sets


@pytest.mark.parametrize(("active", "expected"), [(True, [False]), (False, [])])
def test_disconnect_resets_the_active_flag_only_when_active(
    active: bool, expected: list[bool]
) -> None:
    stub, sets = _stub(active)

    ProxyPlugin._eventcb_mud_disconnected(stub)

    assert sets == expected


def test_callback_is_registered_on_the_disconnect_event() -> None:
    registrations = ProxyPlugin._eventcb_mud_disconnected.event_registration

    assert [r["event_name"] for r in registrations] == [MUD_DISCONNECT_EVENT]


def test_initialize_adds_the_disconnect_event() -> None:
    stub = MagicMock()
    stub.plugin_id = "plugins.core.proxy"
    adds: list[tuple[Any, ...]] = []

    def api(name: str) -> Any:
        if name == "plugins.core.events:event.add":
            return lambda *a, **k: adds.append((a, k))
        return MagicMock()

    stub.api.side_effect = api
    ProxyPlugin._phook_initialize(stub)

    assert any(a[0] == MUD_DISCONNECT_EVENT_SPEC.name for a, _ in adds)
