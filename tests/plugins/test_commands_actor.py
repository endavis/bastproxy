"""Tests that a command runs under a tracking actor (#43)."""

from unittest.mock import MagicMock

import pytest

from bastproxy.libs import argp
from bastproxy.libs.records.rtypes.networkdata import NetworkDataLine
from bastproxy.plugins.core.commands.libs import _command
from bastproxy.plugins.core.commands.libs._command import CommandClass


@pytest.fixture(autouse=True)
def _patch_command_module(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(_command, "API", MagicMock())
    monkeypatch.setattr(_command, "CmdArgsRecord", lambda owner, data, **kw: dict(data))


def test_command_changes_carry_the_command_actor() -> None:
    line = NetworkDataLine("a")

    def function() -> bool:
        line.line = "changed"
        return True

    parser = argp.ArgumentParser(add_help=False)
    parser.add_argument("-h", "--help", action="store_true")
    CommandClass("plugins.test43", "cmd", function, parser).run("")
    assert line.tracking_changes()[-1].actor == "plugins.test43:cmd"
