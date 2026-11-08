"""Regression guard for the timers, triggers, watch and libs.timing renames (#170)."""

import pytest

from tests.plugins.test_api_name_grammar import (
    SRC,
    api_name_error,
    collect_registrations,
)

TIMING = "libs.timing"
TIMERS = "plugins.core.timers"
TRIGGERS = "plugins.core.triggers"
WATCH = "plugins.core.watch"

RENAMES: dict[tuple[str, str], str] = {
    (TIMING, "toggle"): "timing.toggle",
    (TIMING, "start"): "timing.start",
    (TIMING, "finish"): "timing.finish",
    (TIMERS, "has.timer"): "timer.exists",
    (TIMERS, "get.timer.next.fire"): "timer.next.fire.get",
    (TIMERS, "add.timer"): "timer.add",
    (TIMERS, "remove.data.for.plugin"): "timer.remove.for.plugin",
    (TIMERS, "remove.timer"): "timer.remove",
    (TIMERS, "toggle.timer"): "timer.toggle",
    (TRIGGERS, "remove.data.for.owner"): "trigger.remove.for.owner",
    (WATCH, "remove.all.data.for.plugin"): "watch.remove.for.plugin",
}

CASES = sorted(RENAMES.items())


def test_eleven_renames() -> None:
    assert len(RENAMES) == 11


@pytest.mark.parametrize(("old", "new"), CASES)
def test_new_name_registered_and_old_gone(old: tuple[str, str], new: str) -> None:
    registrations = collect_registrations()[0]
    assert (old[0], new) in registrations
    assert old not in registrations


@pytest.mark.parametrize(("old", "new"), CASES)
def test_new_name_passes_grammar(old: tuple[str, str], new: str) -> None:
    assert api_name_error(new) is None


def test_no_source_calls_an_old_name() -> None:
    needles = [f"{TIMING}:{old[1]}" if old[0] == TIMING else f":{old[1]}" for old in RENAMES]
    offenders: list[str] = []
    for path in SRC.rglob("*.py"):
        text = path.read_text()
        offenders.extend(f"{path}: {n}" for n in needles if f'{n}"' in text)
    assert offenders == []
