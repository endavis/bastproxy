"""Tests for the proxy resource command options (#642)."""

from typing import Any
from unittest.mock import MagicMock

import pytest

from bastproxy.plugins.core.proxy.plugin._proxy import ProxyPlugin

TABLES = ("Network Addresses", "Listening Ports", "Connected Ports", "Open Files")


def _run(**args: bool) -> list[str]:
    values = {"networkinterfaces": True, "openfiles": True, "ports": True, **args}
    stub = MagicMock()

    def api(name: str) -> Any:
        if name == "plugins.core.commands:command.current.args.get":
            return lambda: values
        if name == "plugins.core.commands:output.header.format":
            return lambda title: [f"== {title} =="]
        if name == "plugins.core.utils:table.format":
            return lambda title, *_a, **_k: [f"TABLE {title}"]
        return MagicMock()

    stub.api.side_effect = api
    result = ProxyPlugin._command_resource(stub)
    assert result.success is True
    message: list[str] = result.message
    return message


def test_resource_no_options_shows_every_section() -> None:
    msg = _run()
    for title in TABLES:
        assert f"TABLE {title}" in msg


@pytest.mark.parametrize(
    ("option", "hidden"),
    [
        ("networkinterfaces", ("Network Addresses",)),
        ("openfiles", ("Open Files",)),
        ("ports", ("Listening Ports", "Connected Ports")),
    ],
)
def test_resource_option_hides_its_section(option: str, hidden: tuple[str, ...]) -> None:
    msg = _run(**{option: False})
    for title in TABLES:
        assert (f"TABLE {title}" in msg) is (title not in hidden)


def test_resource_option_help_says_hide() -> None:
    import inspect

    source = inspect.getsource(ProxyPlugin)
    assert "show network interfaces in output" not in source
    assert "show open files in output" not in source
    assert "hide network ports from the output" in source
