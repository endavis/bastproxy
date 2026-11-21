"""debug.api detail and call return a failure when they fail (#689)."""

from collections.abc import Callable
from typing import Any
from unittest.mock import MagicMock

from bastproxy.plugins.debug.api.plugin._api import APIPlugin


def _stub(args: dict[str, Any], target: Callable[..., Any] | None = None) -> MagicMock:
    stub = MagicMock()

    def api(name: str) -> Callable[..., Any]:
        if name == "plugins.core.commands:command.current.args.get":
            return lambda: args
        if name == "libs.api:api.detail.get":
            return lambda *_a, **_k: ["d"]
        if target is not None and name == args.get("api"):
            return target
        raise AssertionError(name)

    stub.api = api
    stub.dump_object_as_string = lambda value: "ok"
    return stub


_DETAIL = {"stats": False, "statsdetail": "", "noplugin": False, "show_code": False}


def test_detail_without_api_fails() -> None:
    result = APIPlugin._command_detail(_stub({"api": "", **_DETAIL}))
    assert result.success is False
    assert result.message == ["Please provide an api to detail"]


def test_detail_with_api_succeeds() -> None:
    result = APIPlugin._command_detail(_stub({"api": "libs.api:x", **_DETAIL}))
    assert result.success is True
    assert result.message == ["d"]


def test_call_error_fails() -> None:
    def boom(*_a: Any) -> None:
        raise RuntimeError("boom")

    result = APIPlugin._command_call(_stub({"api": "plugins.nosuch:x", "arguments": []}, boom))
    assert result.success is False
    assert result.message[0] == "Api returned an error:"
    assert any("boom" in line for line in result.message)


def test_call_success() -> None:
    result = APIPlugin._command_call(
        _stub({"api": "plugins.nosuch:x", "arguments": []}, lambda *_a: 5)
    )
    assert result.success is True
    assert result.message[0] == "Api returned:"
