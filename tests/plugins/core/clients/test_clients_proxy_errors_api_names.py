"""Regression guard for the plugins.core.clients, proxy and errors renames (#168)."""

from pathlib import Path

import pytest

from tests.plugins.test_api_name_grammar import (
    SRC,
    api_name_error,
    collect_registrations,
)

CLIENTS = "plugins.core.clients"
ERRORS = "plugins.core.errors"
PROXY = "plugins.core.proxy"

RENAMES: dict[tuple[str, str], str] = {
    (CLIENTS, "get.client"): "client.get",
    (CLIENTS, "send.to.client"): "client.send",
    (CLIENTS, "client.banned.check"): "client.is.banned",
    (CLIENTS, "client.logged.in"): "client.logged.in.set",
    (CLIENTS, "client.logged.in.view.only"): "client.logged.in.set.view.only",
    (CLIENTS, "get.all.clients"): "client.list",
    (CLIENTS, "get.clients.formatted"): "client.list.formatted",
    (ERRORS, "add"): "error.add",
    (ERRORS, "get"): "error.list",
    (ERRORS, "clear.all.errors"): "error.clear",
    (PROXY, "is.mud.connected"): "mud.is.connected",
    (PROXY, "get.mud.connection"): "mud.connection.get",
    (PROXY, "shutdown"): "proxy.shutdown",
    (PROXY, "restart"): "proxy.restart",
}

CASES = sorted(RENAMES.items())


def _owner_file(owner: str) -> Path:
    name = owner.rsplit(".", 1)[1]
    return SRC / "plugins" / "core" / name / "plugin" / f"_{name}.py"


def test_fourteen_renames() -> None:
    assert len(RENAMES) == 14


@pytest.mark.parametrize(("old", "new"), CASES)
def test_new_name_registered_and_old_gone(old: tuple[str, str], new: str) -> None:
    registrations = collect_registrations()[0]
    assert (old[0], new) in registrations
    assert old not in registrations


@pytest.mark.parametrize(("old", "new"), CASES)
def test_new_name_passes_grammar(old: tuple[str, str], new: str) -> None:
    assert api_name_error(new) is None


def test_no_source_calls_an_old_name() -> None:
    # Needles end at the closing quote: client.logged.in is a prefix of its new name.
    offenders: list[str] = []
    for path in SRC.rglob("*.py"):
        text = path.read_text()
        offenders.extend(f'{path}: {o}:{n}"' for (o, n) in RENAMES if f'{o}:{n}"' in text)
    for owner, old in RENAMES:
        path = _owner_file(owner)
        needle = f'{{self.plugin_id}}:{old}"'
        if needle in path.read_text():
            offenders.append(f"{path}: {needle}")
    assert offenders == []
