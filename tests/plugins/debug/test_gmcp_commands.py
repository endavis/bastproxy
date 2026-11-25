"""debug.gmcp.cache and debug.gmcp.send inspect and send GMCP (#784)."""

import argparse
import shlex
from collections.abc import Callable
from types import SimpleNamespace
from typing import Any
from unittest.mock import MagicMock

import pytest

from bastproxy.plugins.core.colors.libs._tokenizer import escape_at
from bastproxy.plugins.debug.gmcp.plugin import _gmcp
from bastproxy.plugins.debug.gmcp.plugin._gmcp import GMCPPlugin, _parse_payload, _split_payload

_CACHE = {"Char.Vitals": {"hp": 10, "mana": 5}, "Char.Status": {"state": 3}}


def _get_value(path: str, default: Any = None) -> Any:
    """A tiny stand-in for gmcp.value.get over _CACHE (exact key, or key plus a field)."""
    if path in _CACHE:
        return _CACHE[path]
    head, _, field = path.rpartition(".")
    if head in _CACHE and field in _CACHE[head]:
        return _CACHE[head][field]
    return default


def _stub(
    args: Any, *, cache: dict[str, Any] | None = None, send_result: bool = True
) -> tuple[MagicMock, MagicMock]:
    """A plugin stand-in whose api() serves the three APIs the commands use."""
    sender = MagicMock(return_value=send_result)
    cache_data = _CACHE if cache is None else cache
    table: dict[str, Callable[..., Any]] = {
        "plugins.core.commands:command.current.args.get": lambda: args,
        "plugins.core.colors:colorcode.escape": escape_at,
        "libs.net.protocols:gmcp.cache.get": lambda: cache_data,
        "libs.net.protocols:gmcp.value.get": _get_value,
        "libs.net.protocols:gmcp.send": sender,
    }
    stub = MagicMock()
    stub.api = lambda name: table[name]
    return stub, sender


def _args(arg_string: str) -> SimpleNamespace:
    """What the command sees: a mapping-like record with an arg_string attribute."""
    parser = _parser(GMCPPlugin._command_send)
    parsed = vars(parser.parse_args(shlex.split(arg_string)))

    class _Args(dict[str, Any]):
        pass

    record = _Args(parsed)
    record.arg_string = arg_string  # type: ignore[attr-defined]  # test double attribute
    return record  # type: ignore[return-value]


def _parser(func: Any) -> argparse.ArgumentParser:
    data = func.command_data
    parser = argparse.ArgumentParser(**data.argparse["kwargs"])
    for argument in data.arguments:
        parser.add_argument(*argument["args"], **argument["kwargs"])
    return parser


def _cache_args(module: str = "") -> dict[str, str]:
    return {"module": module}


def test_cache_lists_modules() -> None:
    stub, _ = _stub(_cache_args())
    result = GMCPPlugin._command_cache(stub)
    assert result.success is True
    assert result.message == ["Cached GMCP modules: 2", "    Char.Status", "    Char.Vitals"]


def test_cache_empty() -> None:
    stub, _ = _stub(_cache_args(), cache={})
    result = GMCPPlugin._command_cache(stub)
    assert result.success is True
    assert result.message == ["No GMCP modules are cached"]


def test_cache_module_json() -> None:
    stub, _ = _stub(_cache_args("Char.Vitals"))
    result = GMCPPlugin._command_cache(stub)
    assert result.success is True
    assert result.message == ["{", '  "hp": 10,', '  "mana": 5', "}"]


def test_cache_scalar_path() -> None:
    stub, _ = _stub(_cache_args("Char.Vitals.hp"))
    result = GMCPPlugin._command_cache(stub)
    assert result.success is True
    assert result.message == ["10"]


def test_cache_absent_module() -> None:
    stub, _ = _stub(_cache_args("Room.@rInfo"))
    result = GMCPPlugin._command_cache(stub)
    assert result.success is False
    assert result.message == ["No cached GMCP value for Room.@@rInfo"]


def test_cache_escapes_colour_codes_and_keeps_non_ascii() -> None:
    value = {"name": "@rRed@w é"}
    stub, _ = _stub(_cache_args("X"), cache={"X": value})
    stub.api = lambda name: {
        "plugins.core.commands:command.current.args.get": lambda: _cache_args("X"),
        "plugins.core.colors:colorcode.escape": escape_at,
        "libs.net.protocols:gmcp.value.get": lambda path, default=None: value,
    }[name]
    result = GMCPPlugin._command_cache(stub)
    assert result.message[1] == '  "name": "@@rRed@@w é"'


def test_cache_listing_escapes_names() -> None:
    stub, _ = _stub(_cache_args(), cache={"A.@rB": {}})
    result = GMCPPlugin._command_cache(stub)
    assert result.message[1] == "    A.@@rB"


def test_send_bare_package() -> None:
    stub, sender = _stub(_args("request"))
    result = GMCPPlugin._command_send(stub)
    assert result.success is True
    sender.assert_called_once_with("request", None)


def test_send_quoted_package() -> None:
    stub, sender = _stub(_args('"request char"'))
    result = GMCPPlugin._command_send(stub)
    assert result.success is True
    sender.assert_called_once_with("request char", None)


def test_send_raw_json() -> None:
    stub, sender = _stub(_args('Char.Test {"a":  1, "b": [1, 2]}'))
    result = GMCPPlugin._command_send(stub)
    assert result.success is True
    sender.assert_called_once_with("Char.Test", {"a": 1, "b": [1, 2]})


def test_send_single_quoted_json() -> None:
    stub, sender = _stub(_args("Char.Test '{\"a\": 1}'"))
    result = GMCPPlugin._command_send(stub)
    assert result.success is True
    sender.assert_called_once_with("Char.Test", {"a": 1})


def test_send_json_null_sends_bare_package() -> None:
    stub, sender = _stub(_args("Char.Test null"))
    GMCPPlugin._command_send(stub)
    sender.assert_called_once_with("Char.Test", None)


def test_send_invalid_json_sends_nothing() -> None:
    stub, sender = _stub(_args("Char.Test {nope"))
    result = GMCPPlugin._command_send(stub)
    assert result.success is False
    assert "not valid JSON" in result.message[0]
    sender.assert_not_called()


def test_send_failure_is_reported() -> None:
    stub, sender = _stub(_args("request"), send_result=False)
    result = GMCPPlugin._command_send(stub)
    assert result.success is False
    assert "Could not send GMCP request" in result.message[0]
    sender.assert_called_once_with("request", None)


def test_parser_arguments() -> None:
    parser = _parser(GMCPPlugin._command_send)
    parsed = parser.parse_args(["Char.Test", "{}", "x"])
    assert parsed.module == "Char.Test"
    assert parsed.data == ["{}", "x"]
    assert parser.parse_args(["Char.Test"]).data == []
    cache = _parser(GMCPPlugin._command_cache)
    assert cache.parse_args([]).module == ""
    assert cache.parse_args(["Char.Vitals"]).module == "Char.Vitals"


def test_send_flags() -> None:
    kwargs = GMCPPlugin._command_send.command_data.command["kwargs"]
    assert kwargs["literal_args"] is True
    assert kwargs["show_in_history"] is False
    assert "literal_args" not in GMCPPlugin._command_cache.command_data.command["kwargs"]


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("pkg", ("pkg", "")),
        ("pkg   ", ("pkg", "")),
        ('pkg {"a":   1}', ("pkg", '{"a":   1}')),
        ('"request char" 5', ("request char", "5")),
        ("pkg 'x y'", ("pkg", "'x y'")),
        ("", ("", "")),
        ('"unterminated', ("", "")),
    ],
)
def test_split_payload(text: str, expected: tuple[str, str]) -> None:
    assert _split_payload(text) == expected


def test_parse_payload() -> None:
    assert _parse_payload("", []) == (True, None)
    assert _parse_payload('{"a": 1}', []) == (True, {"a": 1})
    assert _parse_payload("'[1, 2]'", ["[1, 2]"]) == (True, [1, 2])
    ok, error = _parse_payload("{nope", ["{nope"])
    assert ok is False
    assert isinstance(error, str)
    assert error


def test_module_exports_plugin() -> None:
    from bastproxy.plugins.debug.gmcp import plugin

    assert plugin.Plugin is GMCPPlugin
    assert _gmcp.GMCPPlugin is GMCPPlugin
