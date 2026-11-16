"""Regression tests for #504: usage prog names the owning plugin, not the commands plugin."""

# Standard Library
from collections.abc import Callable
from typing import Any

# Local
from .test_add_by_func_bad_placeholder import (
    CommandsPlugin,
    _FakeTarget,
    _make,
    _stub_command_class,
)

__all__ = ["_stub_command_class"]


class _FormatCommands:
    def __init__(self) -> None:
        self.plugin_id = "plugins.core.commands"
        self.commands_list: list[str] = []
        self.captured: list[Any] = []

    def api(self, name: str) -> Callable[..., Any]:
        if name == "plugins.core.commands:command.format":
            return lambda plugin_id, command: f"#bp.{plugin_id.removeprefix('plugins.')}.{command}"
        raise AssertionError(name)

    def update_command(self, plugin_id: str, command_name: str, command: Any) -> None:
        self.captured.append(command)


def test_prog_uses_owning_plugin_id() -> None:
    target = _FakeTarget()
    target.plugin_id = "plugins.core.proxy"
    fake = _FormatCommands()
    CommandsPlugin._api_command_add_by_func(fake, _make(target, "_command_details"))
    parser = fake.captured[0].args[3]
    assert parser.prog == "#bp.core.proxy.details"
