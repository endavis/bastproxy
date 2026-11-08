"""Tests for cmdq type cleanup on plugin unload and type.add (#122)."""

from typing import Any
from unittest.mock import MagicMock

from bastproxy.plugins.core.cmdq.plugin._cmdq import CMDQPlugin

PID = "plugins.test.a"
OTHER = "plugins.test.b"


def _stub() -> MagicMock:
    """Build a stub cmdq plugin with real containers and a routing api."""
    stub = MagicMock()
    stub.plugin_id = "plugins.core.cmdq"
    stub.cmds = {}
    stub.current_command = {}
    stub.queue = []
    stub.timing_uid = None
    calls: list[str] = []
    stub.calls = calls

    def api(name: str) -> Any:
        calls.append(name)
        if name == "plugins.core.cmdq:type.remove":
            return lambda t: CMDQPlugin._api_type_remove(stub, t)
        if name == "plugins.core.events:event.current.record.get":
            return lambda: {"plugin_id": PID}
        if name == "plugins.core.cmdq:remove.mud.commands.for.plugin":
            return lambda p: CMDQPlugin._api_remove_mud_commands_for_plugin(stub, p)
        if name == "libs.api:get.caller.owner":
            return lambda **k: PID
        return lambda *a, **k: None

    stub.api = api
    return stub


def test_unload_removes_owned_types() -> None:
    """Unloading the owner removes its types, keeps others, raises nothing."""
    stub = _stub()
    CMDQPlugin._api_type_add(stub, "t1", "cmd1", "^a$", owner=PID, plugin=True)
    CMDQPlugin._api_type_add(stub, "t2", "cmd2", "^b$", owner=PID, plugin=True)
    CMDQPlugin._api_type_add(stub, "t3", "cmd3", "^c$", owner=OTHER, plugin=True)

    CMDQPlugin._eventcb_plugin_unloaded(stub)

    assert list(stub.cmds) == ["t3"]


def test_type_add_without_current_command() -> None:
    """type.add works when no command is current."""
    stub = _stub()

    CMDQPlugin._api_type_add(stub, "t1", "cmd1", "^a$")

    assert stub.cmds["t1"]["owner"] == PID


def test_timing_uses_registered_api() -> None:
    """start/finish use libs.timing:start/finish with the returned uid."""
    stub = _stub()
    seen: list[tuple[str, Any]] = []

    def api(name: str) -> Any:
        def call(*a: Any, **k: Any) -> Any:
            seen.append((name, a))
            return "uid1" if name == "libs.timing:start" else None

        return call

    stub.api = api
    CMDQPlugin._api_start(stub, "t1")
    stub.current_command = {"ctype": "t1"}
    stub._finish_timing = lambda: CMDQPlugin._finish_timing(stub)
    stub.sendnext = lambda: None
    CMDQPlugin._api_finish(stub, "t1")

    assert ("libs.timing:start", ("cmd_t1",)) in seen
    assert ("libs.timing:finish", ("uid1",)) in seen
