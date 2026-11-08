"""Regression guard for the plugins.core.log and plugins.core.colors renames (#169)."""

import pytest

from tests.plugins.test_api_name_grammar import (
    SRC,
    api_name_error,
    collect_registrations,
)

LOG = "plugins.core.log"
COLORS = "plugins.core.colors"

RENAMES: dict[tuple[str, str], str] = {
    (COLORS, "color.length.difference"): "color.length.difference.get",
    (LOG, "get.level.color"): "log.level.color.get",
    (LOG, "can.log.to.console"): "logger.console.is.enabled",
    (LOG, "can.log.to.file"): "logger.file.is.enabled",
    (LOG, "can.log.to.client"): "logger.client.is.enabled",
    (LOG, "set.log.to.client"): "logger.client.level.set",
    (LOG, "set.log.to.console"): "logger.console.level.set",
    (LOG, "set.log.to.file"): "logger.file.level.set",
    (LOG, "clean.types"): "logger.type.clean",
}

CASES = sorted(RENAMES.items())


def test_nine_renames() -> None:
    assert len(RENAMES) == 9


@pytest.mark.parametrize(("old", "new"), CASES)
def test_new_name_registered_and_old_gone(old: tuple[str, str], new: str) -> None:
    registrations = collect_registrations()[0]
    assert (old[0], new) in registrations
    assert old not in registrations


@pytest.mark.parametrize(("old", "new"), CASES)
def test_new_name_passes_grammar(old: tuple[str, str], new: str) -> None:
    assert api_name_error(new) is None


def test_no_source_calls_an_old_name() -> None:
    # The closing quote is part of the needle: the new name
    # color.length.difference.get starts with the old name, so a plain
    # substring scan would flag it.
    needles = [f':{old[1]}"' for old in RENAMES]
    offenders: list[str] = []
    for path in SRC.rglob("*.py"):
        text = path.read_text()
        offenders.extend(f"{path}: {n}" for n in needles if n in text)
    assert offenders == []
