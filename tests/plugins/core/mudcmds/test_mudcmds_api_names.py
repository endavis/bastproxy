"""Regression guard for the plugins.core.cmdq to plugins.core.mudcmds rename (#172)."""

import pytest

from tests.plugins.test_api_name_grammar import (
    SRC,
    api_name_error,
    collect_registrations,
)

OLD = "plugins.core.cmdq"
NEW = "plugins.core.mudcmds"

RENAMES: dict[str, str] = {
    "remove.mud.commands.for.plugin": "type.remove.for.plugin",
    "start": "command.start",
    "finish": "command.finish",
    "queue.add.command": "command.queue",
}

CASES = sorted(RENAMES.items())


def test_four_renames() -> None:
    assert len(RENAMES) == 4


@pytest.mark.parametrize(("old", "new"), CASES)
def test_new_name_registered_and_old_gone(old: str, new: str) -> None:
    registrations = collect_registrations()[0]
    assert (NEW, new) in registrations
    assert (NEW, old) not in registrations
    assert (OLD, old) not in registrations


@pytest.mark.parametrize(("old", "new"), CASES)
def test_new_name_passes_grammar(old: str, new: str) -> None:
    assert api_name_error(new) is None


def test_unchanged_names_registered() -> None:
    registrations = collect_registrations()[0]
    assert (NEW, "type.add") in registrations
    assert (NEW, "type.remove") in registrations


def test_old_plugin_id_has_no_registrations() -> None:
    registrations = collect_registrations()[0]
    assert [key for key in registrations if key[0] == OLD] == []


def test_no_source_mentions_old_plugin_or_names() -> None:
    needles = [OLD, "core/cmdq", "remove.mud.commands.for.plugin", "queue.add.command"]
    offenders: list[str] = []
    for path in SRC.rglob("*.py"):
        text = path.read_text()
        offenders.extend(f"{path}: {n}" for n in needles if n in text)
    assert offenders == []
    assert not (SRC / "plugins" / "core" / "cmdq").exists()
