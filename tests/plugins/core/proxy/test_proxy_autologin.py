"""Tests for the auto-login callback on the mud connect event (#556)."""

from typing import Any
from unittest.mock import MagicMock

import pytest

from bastproxy.libs.net.mud import MUD_CONNECT_EVENT, MUD_CONNECT_EVENT_SPEC
from bastproxy.plugins.core.proxy.plugin import _proxy
from bastproxy.plugins.core.proxy.plugin._proxy import ProxyPlugin

SENTINEL_PW = "placeholder-secret-not-real"


def _stub(username: str, password: str) -> MagicMock:
    stub = MagicMock()
    stub.plugin_id = "plugins.core.proxy"

    def api(name: str) -> Any:
        if name == "plugins.core.settings:setting.get":
            return lambda _plugin, _setting: username
        if name == "plugins.core.proxy:ssc.mudpw.get":
            return lambda: password
        return MagicMock()

    stub.api.side_effect = api
    return stub


@pytest.fixture
def sent(monkeypatch: pytest.MonkeyPatch) -> list[list[tuple[str, bool]]]:
    calls: list[list[tuple[str, bool]]] = []

    class _Send:
        def __init__(self, data: Any, *args: Any, **kwargs: Any) -> None:
            calls.append([(str(line.line), bool(line.mask_log)) for line in data])

        def __call__(self) -> None:
            return None

    monkeypatch.setattr(_proxy, "SendDataDirectlyToMud", _Send)
    return calls


def test_sends_username_then_password(sent: list[list[tuple[str, bool]]]) -> None:
    ProxyPlugin._eventcb_sendusernameandpw(_stub("someuser", SENTINEL_PW))

    assert [lines[0][0] for lines in sent] == ["someuser", SENTINEL_PW]
    assert [lines[0][1] for lines in sent] == [False, True]


def test_sends_username_only_without_a_password(sent: list[list[tuple[str, bool]]]) -> None:
    ProxyPlugin._eventcb_sendusernameandpw(_stub("someuser", ""))

    assert [lines[0][0] for lines in sent] == ["someuser"]


def test_sends_nothing_without_a_username(sent: list[list[tuple[str, bool]]]) -> None:
    ProxyPlugin._eventcb_sendusernameandpw(_stub("", SENTINEL_PW))

    assert sent == []


def test_callback_is_registered_on_the_connect_event() -> None:
    registrations = ProxyPlugin._eventcb_sendusernameandpw.event_registration

    assert [r["event_name"] for r in registrations] == [MUD_CONNECT_EVENT]


def test_initialize_adds_the_connect_event() -> None:
    stub = MagicMock()
    stub.plugin_id = "plugins.core.proxy"
    adds: list[tuple[Any, ...]] = []

    def api(name: str) -> Any:
        if name == "plugins.core.events:event.add":
            return lambda *a, **k: adds.append((a, k))
        return MagicMock()

    stub.api.side_effect = api
    ProxyPlugin._phook_initialize(stub)

    assert any(a[0] == MUD_CONNECT_EVENT_SPEC.name for a, _ in adds)
