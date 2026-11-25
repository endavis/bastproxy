"""Tests for the auto-login callback on the mud connect event (#556)."""

from typing import Any
from unittest.mock import MagicMock

import pytest

from bastproxy.libs.net.mud import MUD_CONNECT_EVENT, MUD_CONNECT_EVENT_SPEC
from bastproxy.plugins.core.proxy.plugin import _proxy
from bastproxy.plugins.core.proxy.plugin._proxy import ProxyPlugin

SENTINEL_PW = "placeholder-secret-not-real"


def _stub(username: str, password: str, blank_lines: int = 0) -> MagicMock:
    stub = MagicMock()
    stub.plugin_id = "plugins.core.proxy"

    def api(name: str) -> Any:
        if name == "plugins.core.settings:setting.get":
            return lambda _plugin, setting: (
                blank_lines if setting == "autologinblanklines" else username
            )
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


def test_sends_blank_lines_after_the_password(sent: list[list[tuple[str, bool]]]) -> None:
    ProxyPlugin._eventcb_sendusernameandpw(_stub("someuser", SENTINEL_PW, blank_lines=2))

    assert [lines[0][0] for lines in sent] == ["someuser", SENTINEL_PW, "", ""]
    assert [lines[0][1] for lines in sent] == [False, True, False, False]


def test_sends_no_extra_lines_by_default(sent: list[list[tuple[str, bool]]]) -> None:
    ProxyPlugin._eventcb_sendusernameandpw(_stub("someuser", SENTINEL_PW))

    assert len(sent) == 2


def test_sends_no_blank_lines_without_a_password(sent: list[list[tuple[str, bool]]]) -> None:
    ProxyPlugin._eventcb_sendusernameandpw(_stub("someuser", "", blank_lines=2))

    assert [lines[0][0] for lines in sent] == ["someuser"]


def test_blank_lines_are_sent_once_per_connect_event(sent: list[list[tuple[str, bool]]]) -> None:
    # the only trigger is the connect event, which fires once per connection
    registrations = ProxyPlugin._eventcb_sendusernameandpw.event_registration
    assert len(registrations) == 1

    ProxyPlugin._eventcb_sendusernameandpw(_stub("someuser", SENTINEL_PW, blank_lines=1))

    assert [lines[0][0] for lines in sent].count("") == 1


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
