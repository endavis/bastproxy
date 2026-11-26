"""CommandClass owner versus host behaviour (#834)."""

# Standard Library
import logging
from unittest.mock import MagicMock

# 3rd Party
import pytest

# Project
from bastproxy.libs import argp
from bastproxy.libs.records.rtypes.networkdata import NetworkDataLine
from bastproxy.plugins.core.commands import CommandResult
from bastproxy.plugins.core.commands.libs import _command
from bastproxy.plugins.core.commands.libs._command import CommandClass

HOST = "plugins.host"
OWNER = "plugins.owner"


@pytest.fixture
def record_owner(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    owners: list[str] = []

    def record(owner: str, data: dict[str, object], **kw: object) -> dict[str, object]:
        owners.append(owner)
        return dict(data)

    monkeypatch.setattr(_command, "API", MagicMock())
    monkeypatch.setattr(_command, "CmdArgsRecord", record)
    return owners


def _parser() -> argp.ArgumentParser:
    parser = argp.ArgumentParser(add_help=False)
    parser.add_argument("-h", "--help", action="store_true")
    return parser


def test_owner_defaults_to_the_plugin(record_owner: list[str]) -> None:
    command = CommandClass(HOST, "cmd", lambda: CommandResult(True), _parser())
    assert command.owner_id == HOST
    command.run("")
    assert record_owner == [f"{HOST}:cmd"]
    assert "owner=" not in repr(command)


def test_owner_drives_actor_and_record(record_owner: list[str]) -> None:
    line = NetworkDataLine("a")

    def function() -> CommandResult:
        line.line = "changed"
        return CommandResult(True)

    command = CommandClass(HOST, "cmd", function, _parser(), owner_id=OWNER)
    command.run("")
    assert line.tracking_changes()[-1].actor == f"{OWNER}:cmd"
    assert record_owner == [f"{OWNER}:cmd"]
    assert command.plugin_id == HOST
    assert f"owner={OWNER}" in repr(command)


def test_errors_log_to_owner_and_host(
    record_owner: list[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    logged: list[list[str]] = []
    monkeypatch.setattr(_command, "log_to", lambda ids, *a, **k: logged.append(list(ids)))

    def boom() -> CommandResult:
        raise ValueError("x")

    CommandClass(HOST, "cmd", boom, _parser(), owner_id=OWNER).run("")
    assert logged[0] == [OWNER, HOST, "plugins.core.commands"]
    logged.clear()
    CommandClass(HOST, "cmd", boom, _parser()).run("")
    assert logged[0] == [HOST, "plugins.core.commands"]
    assert logging.ERROR
