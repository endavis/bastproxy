"""Tests that a second connect during an in-progress connect is refused (#306)."""

from typing import Any
from unittest.mock import MagicMock

from bastproxy.plugins.core.proxy.plugin._proxy import ProxyPlugin


def _stub(task_add: MagicMock, settings: dict[str, Any] | None = None) -> MagicMock:
    stub = MagicMock()
    stub.mud_connection = None
    stub.plugin_id = "plugins.core.proxy"

    def get_setting(_plugin_id: str, name: str) -> Any:
        if settings is not None and name in settings:
            return settings[name]
        return "x"

    def api(name: str) -> Any:
        if name == "libs.asynch:task.add":
            return task_add
        if name == "plugins.core.settings:setting.get":
            return get_setting
        return lambda *_a, **_k: "x"

    stub.api.side_effect = api
    return stub


def test_second_connect_while_connecting_is_refused() -> None:
    task_add = MagicMock()
    stub = _stub(task_add)

    result = ProxyPlugin._command_connect(stub)
    first = result.message
    conn = stub.mud_connection
    result = ProxyPlugin._command_connect(stub)
    second = result.message

    assert first == ["Connecting to the mud"]
    assert conn.connecting is True
    assert "already connecting" in second[0]
    assert stub.mud_connection is conn
    assert task_add.call_count == 1


def test_connect_retries_after_a_failure() -> None:
    task_add = MagicMock()
    stub = _stub(task_add)

    ProxyPlugin._command_connect(stub)
    stub.mud_connection.connecting = False  # what a failed connect_to_mud does
    result = ProxyPlugin._command_connect(stub)
    msg = result.message

    assert msg == ["Connecting to the mud"]
    assert task_add.call_count == 2


def test_connect_refused_when_connected() -> None:
    task_add = MagicMock()
    stub = _stub(task_add)
    stub.mud_connection = MagicMock(connected=True, connecting=False)

    result = ProxyPlugin._command_connect(stub)
    msg = result.message

    assert "currently connected" in msg[0]
    task_add.assert_not_called()


def test_disconnect_while_connecting_does_not_drop_the_connection() -> None:
    stub = _stub(MagicMock())
    conn = MagicMock(connected=False, connecting=True)
    stub.mud_connection = conn

    result = ProxyPlugin._command_disconnect(stub)
    msg = result.message

    assert "connecting" in msg[0]
    assert stub.mud_connection is conn
    conn.disconnect_from_mud.assert_not_called()


def test_info_shows_connecting() -> None:
    stub = _stub(MagicMock())
    stub.mud_connection = MagicMock(connected=False, connecting=True)
    stub.api.proxy_start_time = None
    stub.api.side_effect = lambda name: lambda *a, **k: ["H"] if "header" in name else []

    result = ProxyPlugin._command_info(stub)
    msg = result.message

    assert any("connecting" in line for line in msg)
    assert not any("disconnected" in line for line in msg)


def _refused(settings: dict[str, Any]) -> tuple[Any, list[str], MagicMock, MagicMock]:
    task_add = MagicMock()
    stub = _stub(task_add, settings)
    result = ProxyPlugin._command_connect(stub)
    return result, result.message, task_add, stub


def test_connect_refused_when_mudhost_unset() -> None:
    result, msg, task_add, stub = _refused({"mudhost": "", "mudport": 4000})

    assert result.success is False
    assert any("mudhost" in line for line in msg)
    assert not any("mudport" in line for line in msg)
    assert stub.mud_connection is None
    task_add.assert_not_called()


def test_connect_refused_when_mudport_zero() -> None:
    result, msg, task_add, stub = _refused({"mudhost": "host", "mudport": 0})

    assert result.success is False
    assert any("mudport" in line for line in msg)
    assert not any("mudhost" in line for line in msg)
    assert stub.mud_connection is None
    task_add.assert_not_called()


def test_connect_refused_when_both_unset() -> None:
    result, msg, task_add, stub = _refused({"mudhost": "", "mudport": 0})

    assert result.success is False
    assert any("mudhost 'host'" in line for line in msg)
    assert any("mudport 'port'" in line for line in msg)
    assert stub.mud_connection is None
    task_add.assert_not_called()


def test_connect_proceeds_when_both_set() -> None:
    _result, msg, task_add, stub = _refused({"mudhost": "host", "mudport": 4000})

    assert msg == ["Connecting to the mud"]
    assert stub.mud_connection is not None
    assert task_add.call_count == 1
