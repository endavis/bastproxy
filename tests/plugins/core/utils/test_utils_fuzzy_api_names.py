"""Regression guard for the plugins.core.utils and plugins.core.fuzzy renames (#167)."""

import pytest

from tests.plugins.test_api_name_grammar import (
    SRC,
    api_name_error,
    collect_registrations,
)

FUZZY = "plugins.core.fuzzy"
UTILS = "plugins.core.utils"

RENAMES: dict[tuple[str, str], str] = {
    (FUZZY, "get.best.match"): "string.match.best",
    (FUZZY, "get.top.matches"): "string.match.top",
    (UTILS, "format.list.into.columns"): "column.format",
    (UTILS, "dump.object.as.string"): "object.dump",
    (UTILS, "get.keys.from.dict"): "dict.key.list",
    (UTILS, "dedent.list.of.strings"): "string.dedent",
    (UTILS, "convert.timedelta.to.string"): "timedelta.to.string",
    (UTILS, "convert.to.readable.number"): "number.to.readable",
    (UTILS, "convert.seconds.to.dhms"): "seconds.to.dhms",
    (UTILS, "format.time"): "timelength.format",
    (UTILS, "verify.value"): "value.verify",
    (UTILS, "center.colored.string"): "string.center.colored",
    (UTILS, "check.list.for.match"): "string.match.in.list",
    (UTILS, "convert.timelength.to.secs"): "timelength.to.seconds",
    (UTILS, "convert.data.to.output.table"): "table.format",
    (UTILS, "cap.line"): "line.cap",
}

CASES = sorted(RENAMES.items())


def test_sixteen_renames() -> None:
    assert len(RENAMES) == 16


@pytest.mark.parametrize(("old", "new"), CASES)
def test_new_name_registered_and_old_gone(old: tuple[str, str], new: str) -> None:
    registrations = collect_registrations()[0]
    assert (old[0], new) in registrations
    assert old not in registrations


@pytest.mark.parametrize(("old", "new"), CASES)
def test_new_name_passes_grammar(old: tuple[str, str], new: str) -> None:
    assert api_name_error(new) is None


def test_no_source_calls_an_old_name() -> None:
    needles = [f":{old[1]}" for old in RENAMES]
    offenders: list[str] = []
    for path in SRC.rglob("*.py"):
        text = path.read_text()
        offenders.extend(f"{path}: {n}" for n in needles if n in text)
    assert offenders == []
