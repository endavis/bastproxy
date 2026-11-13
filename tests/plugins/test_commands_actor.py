"""Tests that a command runs under a tracking actor (#43)."""

from unittest.mock import MagicMock

import pytest

from bastproxy.libs import argp
from bastproxy.libs.context import get_command_args
from bastproxy.libs.records.rtypes.networkdata import NetworkDataLine
from bastproxy.plugins.core.commands import CommandResult
from bastproxy.plugins.core.commands.libs import _command
from bastproxy.plugins.core.commands.libs._command import CommandClass


@pytest.fixture(autouse=True)
def _patch_command_module(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(_command, "API", MagicMock())
    monkeypatch.setattr(_command, "CmdArgsRecord", lambda owner, data, **kw: dict(data))


def test_command_changes_carry_the_command_actor() -> None:
    line = NetworkDataLine("a")

    def function() -> CommandResult:
        line.line = "changed"
        return CommandResult(True)

    parser = argp.ArgumentParser(add_help=False)
    parser.add_argument("-h", "--help", action="store_true")
    CommandClass("plugins.test43", "cmd", function, parser).run("")
    assert line.tracking_changes()[-1].actor == "plugins.test43:cmd"


def test_command_args_are_set_while_the_command_runs() -> None:
    seen: dict[str, object] = {}

    def function() -> CommandResult:
        seen["args"] = dict(get_command_args())
        return CommandResult(True)

    parser = argp.ArgumentParser(add_help=False)
    parser.add_argument("-h", "--help", action="store_true")
    parser.add_argument("--flag", default="x")
    CommandClass("plugins.test248", "cmd", function, parser).run("--flag y")
    assert seen["args"] == {"help": False, "flag": "y"}
    assert dict(get_command_args()) == {}
