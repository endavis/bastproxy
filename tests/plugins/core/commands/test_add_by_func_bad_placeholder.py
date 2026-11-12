"""Regression tests for #391: a bad placeholder skips only that command."""

# Standard Library
import logging
from collections.abc import Callable
from types import MethodType
from typing import Any

# 3rd Party
import pytest

# Project
from bastproxy.plugins.core.commands.plugin import _commands
from bastproxy.plugins.core.commands.plugin._commands import CommandsPlugin

PLUGIN_ID = "plugins.test.fake"


class _StubCommand:
    """Stand-in for CommandClass, which needs the live api."""

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        self.args = args


@pytest.fixture(autouse=True)
def _stub_command_class(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(_commands, "CommandClass", _StubCommand)
    monkeypatch.setattr(_commands, "log_to", lambda *args, **kwargs: None)


class _Data:
    def __init__(self, command: dict[str, Any], argparse: dict[str, Any], arguments: list[Any]):
        self.command = command
        self.argparse = argparse
        self.arguments = arguments


class _FakeTarget:
    """The plugin that owns the command methods."""

    def __init__(self) -> None:
        self.plugin_id = PLUGIN_ID
        self.name = "fake"


def _make(
    target: _FakeTarget,
    fname: str,
    name: str | None = None,
    description: str = "fine",
    help_text: str = "fine",
) -> MethodType:
    command: dict[str, Any] = {"autoadd": True, "kwargs": {}}
    if name is not None:
        command["name"] = name
    data = _Data(
        command,
        {"kwargs": {"add_help": False, "description": description}},
        [{"args": ["-x"], "kwargs": {"help": help_text}}],
    )

    def _func(self: Any) -> None:
        return None

    _func.__name__ = fname
    _func.command_data = data  # type: ignore[attr-defined]
    return MethodType(_func, target)


class _FakeCommands:
    def __init__(self) -> None:
        self.plugin_id = "plugins.core.commands"
        self.commands_list: list[str] = []
        self.updated: list[str] = []

    def api(self, name: str) -> Callable[..., Any]:
        if name == "plugins.core.commands:command.format":
            return lambda plugin_id, command: f"#bp.{command}"
        raise AssertionError(name)

    def update_command(self, plugin_id: str, command_name: str, command: Any) -> None:
        self.updated.append(command_name)


def _add_all(fake: _FakeCommands, funcs: list[MethodType]) -> None:
    for func in funcs:
        CommandsPlugin._api_command_add_by_func(fake, func)


def test_bad_name_is_skipped_others_register(caplog: pytest.LogCaptureFixture) -> None:
    target = _FakeTarget()
    fake = _FakeCommands()
    funcs = [
        _make(target, "_command_aaa"),
        _make(target, "_command_bad", name="{nope}"),
        _make(target, "_command_zzz"),
    ]
    with caplog.at_level(logging.ERROR):
        _add_all(fake, funcs)
    assert fake.updated == ["aaa", "zzz"]
    assert any(
        "{nope}" in r.getMessage() and "_command_bad" in r.getMessage() for r in caplog.records
    )


def test_bad_description_is_skipped(caplog: pytest.LogCaptureFixture) -> None:
    target = _FakeTarget()
    fake = _FakeCommands()
    funcs = [_make(target, "_command_bad", description="oops {"), _make(target, "_command_ok")]
    with caplog.at_level(logging.ERROR):
        _add_all(fake, funcs)
    assert fake.updated == ["ok"]
    assert any("oops {" in r.getMessage() for r in caplog.records)


def test_bad_argument_help_is_skipped(caplog: pytest.LogCaptureFixture) -> None:
    target = _FakeTarget()
    fake = _FakeCommands()
    funcs = [_make(target, "_command_bad", help_text="100% {x}"), _make(target, "_command_ok")]
    with caplog.at_level(logging.ERROR):
        _add_all(fake, funcs)
    assert fake.updated == ["ok"]
    assert any("{x}" in r.getMessage() for r in caplog.records)


def test_update_commands_for_plugin_continues_after_error(
    caplog: pytest.LogCaptureFixture,
) -> None:
    target = _FakeTarget()
    funcs = [_make(target, "_command_a"), _make(target, "_command_b"), _make(target, "_command_c")]
    added: list[str] = []

    def add(func: MethodType) -> None:
        if func.__name__ == "_command_b":
            raise RuntimeError("boom")
        added.append(func.__name__)

    class _Fake:
        plugin_id = "plugins.core.commands"

        def api(self, name: str) -> Callable[..., Any]:
            if name == "libs.plugins.loader:plugin.instance.get":
                return lambda plugin_id: target
            if name == "plugins.core.commands:command.add.by.func":
                return add
            raise AssertionError(name)

        def get_command_functions_in_object(self, base: Any) -> list[MethodType]:
            return funcs

    with caplog.at_level(logging.ERROR):
        CommandsPlugin.update_commands_for_plugin(_Fake(), PLUGIN_ID)  # type: ignore[arg-type]
    assert added == ["_command_a", "_command_c"]
    assert any("_command_b" in r.getMessage() for r in caplog.records)


def test_add_commands_for_all_plugins_continues_after_error(
    caplog: pytest.LogCaptureFixture,
) -> None:
    seen: list[str] = []

    class _Fake:
        plugin_id = "plugins.core.commands"

        def api(self, name: str) -> Callable[..., Any]:
            if name == "libs.plugins.loader:plugin.list.loaded":
                return lambda: ["p1", "p2", "p3"]
            raise AssertionError(name)

        def update_commands_for_plugin(self, plugin_id: str) -> None:
            if plugin_id == "p2":
                raise RuntimeError("boom")
            seen.append(plugin_id)

    with caplog.at_level(logging.ERROR):
        CommandsPlugin._add_commands_for_all_plugins(_Fake())  # type: ignore[arg-type]
    assert seen == ["p1", "p3"]
    assert any("p2" in r.getMessage() for r in caplog.records)
