"""Tests that the *_data_read events receive NetworkDataLine records."""

from collections.abc import Callable
from typing import Any
from unittest.mock import MagicMock

import pytest

from bastproxy.libs.records.rtypes.clientdata import SendDataDirectlyToClient
from bastproxy.libs.records.rtypes.muddata import SendDataDirectlyToMud
from bastproxy.libs.records.rtypes.networkdata import NetworkData, NetworkDataLine


def _fake_api(calls: list[tuple[str, dict[str, Any]]]) -> Callable[[str], Callable[..., Any]]:
    """Build a fake api that records raise.event calls and mocks the rest."""

    def api(name: str) -> Callable[..., Any]:
        if name == "plugins.core.events:raise.event":

            def raise_event(event_name: str, **kwargs: Any) -> None:
                calls.append((event_name, kwargs))

            return raise_event
        if name == "plugins.core.clients:get.all.clients":
            return lambda uuid_only=False: []
        return MagicMock()

    return api


def _message() -> NetworkData:
    sent = NetworkDataLine("hello", line_type="IO")
    hidden = NetworkDataLine("secret", line_type="IO")
    hidden.send = False
    return NetworkData([sent, hidden])


@pytest.mark.parametrize(
    ("record_cls", "event_name"),
    [
        (SendDataDirectlyToMud, "ev_to_mud_data_read"),
        (SendDataDirectlyToClient, "ev_to_client_data_read"),
    ],
)
def test_read_event_receives_records(
    monkeypatch: pytest.MonkeyPatch, record_cls: type, event_name: str
) -> None:
    calls: list[tuple[str, dict[str, Any]]] = []
    monkeypatch.setattr(record_cls, "_SETUP_EVENTS", True)
    monkeypatch.setattr(NetworkDataLine, "format", lambda self: None)
    record = record_cls(_message())
    record.api = _fake_api(calls)
    record._exec_()

    assert len(calls) == 1
    name, kwargs = calls[0]
    assert name == event_name
    assert kwargs["key_name"] == "line"
    data_list = kwargs["data_list"]
    assert len(data_list) == 1
    assert all(isinstance(item, NetworkDataLine) for item in data_list)
    assert data_list[0].line == "hello"
