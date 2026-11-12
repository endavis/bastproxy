"""Regression tests for #400: dead command state is removed, AddParser is keyword-only."""

# Standard Library
import inspect

# 3rd Party
import pytest

# Project
from bastproxy.plugins.core.commands.libs import _utils
from bastproxy.plugins.core.commands.libs._utils import AddArgument, AddParser
from bastproxy.plugins.core.commands.plugin._commands import CommandsPlugin


def test_positional_argument_raises_type_error() -> None:
    with pytest.raises(TypeError):
        AddParser("x")  # type: ignore[call-arg]


def test_keyword_use_has_no_args_key() -> None:
    @AddParser(description="d")
    def func() -> None:
        return None

    argparse = func.command_data.argparse
    assert "args" not in argparse
    assert argparse["kwargs"]["description"] == "d"
    assert argparse["kwargs"]["add_help"] is False


def test_keyword_use_stacked_with_add_argument() -> None:
    @AddParser(description="d")
    @AddArgument("value", help="v")
    def func() -> None:
        return None

    data = func.command_data
    assert "args" not in data.argparse
    assert data.arguments == [{"args": ("value",), "kwargs": {"help": "v"}}]


def test_removed_names_are_absent() -> None:
    assert not hasattr(_utils, "commands_at_startup")
    for name in ("api_get_all_commands_list", "_api_remove_command"):
        assert not hasattr(CommandsPlugin, name)
    # the two attributes were set in __init__, so look at its source
    init_source = inspect.getsource(CommandsPlugin.__init__)
    assert "no_multiple_commands" not in init_source
    assert "default_help_command" not in init_source
    assert "no_multiple_commands" not in inspect.getsource(CommandsPlugin)
