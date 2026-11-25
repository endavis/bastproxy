"""Tests for the command.literal.args.get API (#816)."""

from unittest.mock import MagicMock

from bastproxy.plugins.core.commands.plugin._commands import CommandLookup, CommandsPlugin


def _get(line: str, command: object) -> tuple[bool | None, MagicMock]:
    stub = MagicMock()
    stub.find_command.return_value = CommandLookup(command, "", True, "", [])  # type: ignore[arg-type]
    return CommandsPlugin._api_command_literal_args_get(stub, line), stub


def test_literal_command_is_true() -> None:
    assert _get("#bp.a.b x", MagicMock(literal_args=True))[0] is True


def test_non_literal_command_is_false() -> None:
    assert _get("#bp.a.b x", MagicMock(literal_args=False))[0] is False


def test_unknown_command_is_none() -> None:
    assert _get("#bp.zz", None)[0] is None


def test_line_is_left_stripped() -> None:
    _, stub = _get("   #bp.a.b x", MagicMock(literal_args=False))
    stub.find_command.assert_called_once_with("#bp.a.b x")
