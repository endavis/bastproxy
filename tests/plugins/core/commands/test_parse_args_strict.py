"""Regression tests for #398: commands reject unknown arguments and abbreviated options."""

# Standard Library
import argparse
from typing import Any
from unittest.mock import MagicMock

# 3rd Party
import pytest

# Project
from bastproxy.libs import argp
from bastproxy.plugins.core.commands import CommandResult
from bastproxy.plugins.core.commands.libs import _command
from bastproxy.plugins.core.commands.libs._command import CommandClass

from .test_add_by_func_bad_placeholder import (
    PLUGIN_ID,
    _add_all,
    _FakeCommands,
    _FakeTarget,
    _make,
    _stub_command_class,
)

__all__ = ["_stub_command_class"]


@pytest.fixture(autouse=True)
def _patch_command_module(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(_command, "API", MagicMock())
    monkeypatch.setattr(_command, "CmdArgsRecord", lambda owner, data, **kw: dict(data))


def _command_with(parser: argp.ArgumentParser, ran: list[bool]) -> CommandClass:
    def function() -> CommandResult:
        ran.append(True)
        return CommandResult(True)

    return CommandClass("plugins.test398", "cmd", function, parser)


def _parser(**kwargs: Any) -> argp.ArgumentParser:
    parser = argp.ArgumentParser(add_help=False, **kwargs)
    parser.add_argument("-h", "--help", action="store_true")
    parser.add_argument("--flag", default="x")
    return parser


def test_unknown_option_is_rejected_with_help() -> None:
    parsed = _command_with(_parser(), []).parse_args("--nope 1")
    assert parsed.success is False
    assert "unrecognized arguments" in parsed.message[0]
    assert "--nope" in parsed.message[0]
    assert any("--flag" in line for line in parsed.message[2:])


def test_extra_positional_is_rejected() -> None:
    parsed = _command_with(_parser(), []).parse_args("stray")
    assert parsed.success is False
    assert "unrecognized arguments: stray" in parsed.message[0]


def test_unknown_option_does_not_run_function() -> None:
    ran: list[bool] = []
    _command_with(_parser(), ran).run("--nope 1")
    assert ran == []


def test_abbreviated_option_is_rejected_without_abbrev() -> None:
    parsed = _command_with(_parser(allow_abbrev=False), []).parse_args("--fl y")
    assert parsed.success is False
    assert "--fl" in parsed.message[0]


def test_full_option_still_works() -> None:
    parsed = _command_with(_parser(allow_abbrev=False), []).parse_args("--flag y")
    assert parsed.success is True
    assert isinstance(parsed.args, argparse.Namespace)
    assert parsed.args.flag == "y"


def test_registered_command_parser_disallows_abbreviations() -> None:
    fake = _FakeCommands()
    fake.updated_commands = []  # type: ignore[attr-defined]
    seen: list[Any] = []

    def update(plugin_id: str, command_name: str, command: Any) -> None:
        seen.append(command)

    fake.update_command = update  # type: ignore[method-assign]
    _add_all(fake, [_make(_FakeTarget(), "_command_aaa")])
    parser = seen[0].args[3]
    assert parser.allow_abbrev is False
    assert seen[0].args[0] == PLUGIN_ID
