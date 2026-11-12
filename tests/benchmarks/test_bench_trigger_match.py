# Project: bastproxy
# Filename: tests/benchmarks/test_bench_trigger_match.py
#
# File Description: Benchmarks for matching a line against the triggers plugin's triggers
#
# By: Bast
"""Benchmark what a line costs in the triggers plugin (audit Q4, issue #358).

Informational, with no gate. This measures the same quantities as Q4 ("What Does a Line Cost?") in
``docs/claude/triggers_system_findings.md``, on the per-trigger matcher of ADR-0007 instead of the
combined regex Q4 measured:

1. ``_eventcb_check_trigger`` per line at 10, 100 and 1,000 enabled triggers, for a line that
   matches nothing, a line that matches the first trigger in priority order and a line that
   matches the last;
2. the time to add 100 triggers one by one through ``trigger.add``.

The real ``TriggersPlugin`` methods run on the stand-in ``Harness`` of
``tests/plugins/core/triggers/conftest.py``. Its event raise is a recording stub, so the figures
are the regex work and the Python around it, not delivering an event. The triggers use generated,
``^``-anchored regexes of six shapes (damage, tells, arrivals, channels, skills, status), each
with one or two named groups and a token that is unique to the trigger, so a line matches exactly
one trigger. Priority is the trigger's index, so index 0 is first and the last index is last in
``_ordered``.

Each timed call runs the same line ``BATCH`` times; divide the reported mean by ``BATCH`` for the
cost of one line. ``harness.raised`` is cleared after each batch so memory does not grow.
"""

from collections.abc import Callable
from typing import Any
from unittest.mock import MagicMock

import pytest

from bastproxy.libs.records.enums import Originated
from bastproxy.libs.records.rtypes.networkdata import NetworkDataLine
from bastproxy.plugins.core.colors.plugin._colors import ColorsPlugin
from tests.plugins.core.triggers.conftest import Harness

ROUNDS = 100
BATCH = 20
SIZES = (10, 100, 1000)
ADD_COUNT = 100
ADD_ROUNDS = 20

# (regex template, line template); {i} is the unique token, groups are named.
SHAPES: tuple[tuple[str, str], ...] = (
    (
        r"^Your (?P<attack>\w+) hits mob{i} for (?P<amount>\d+) damage\.$",
        "Your slash hits mob{i} for 42 damage.",
    ),
    (
        r"^(?P<who>\w+) tells you, 'cmd{i} (?P<msg>.*)'$",
        "Alice tells you, 'cmd{i} hello there'",
    ),
    (
        r"^(?P<who>\w+) arrives from the (?P<dir>north|south|east|west) room{i}\.$",
        "Bob arrives from the north room{i}.",
    ),
    (
        r"^\[chan{i}\] (?P<who>\w+): (?P<msg>.*)$",
        "[chan{i}] Carol: anyone around?",
    ),
    (
        r"^You (?P<verb>feel|begin) (?P<skill>skill{i}) at (?P<pct>\d+)%$",
        "You feel skill{i} at 75%",
    ),
    (
        r"^HP: (?P<hp>\d+)/(?P<maxhp>\d+) status{i}$",
        "HP: 100/120 status{i}",
    ),
)

NO_MATCH_LINE = "The wind rises over the hills and nothing at all happens."


def _regex(index: int) -> str:
    """The regex for trigger ``index``; shapes rotate."""
    return SHAPES[index % len(SHAPES)][0].format(i=index)


def _line_text(index: int) -> str:
    """A line that trigger ``index`` matches and no other trigger does."""
    return SHAPES[index % len(SHAPES)][1].format(i=index)


def _add_trigger(harness: Harness, index: int) -> None:
    """Add trigger ``index``; priority is the index. The return value is not used."""
    harness.add(f"bench{index}", _regex(index), priority=index)


@pytest.fixture
def harness(monkeypatch: pytest.MonkeyPatch) -> Harness:
    """A stand-in triggers plugin with the colour helpers the line needs."""
    colors = MagicMock()
    colors.plugin_id = "plugins.core.colors"
    table: dict[str, Callable[..., Any]] = {
        "plugins.core.colors:ansicode.strip": lambda text: ColorsPlugin._api_ansicode_strip(
            colors, text
        ),
        "plugins.core.colors:ansicode.to.colorcode": lambda text: (
            ColorsPlugin._api_ansicode_to_colorcode(colors, text)
        ),
    }
    monkeypatch.setattr(NetworkDataLine, "api", staticmethod(lambda name: table[name]))
    return Harness(monkeypatch)


def _loaded(harness: Harness, count: int) -> None:
    """Add ``count`` enabled triggers and check the first and last by priority."""
    for index in range(count):
        _add_trigger(harness, index)
    names = harness.ordered_names()
    assert len(names) == count
    assert names[0] == "bench0"
    assert names[-1] == f"bench{count - 1}"


def _set_line(harness: Harness, text: str) -> None:
    """Make ``text`` the current MUD line."""
    harness.line = NetworkDataLine(text, originated=Originated.MUD)
    harness.current_record = {"line": harness.line}


def _batch(harness: Harness) -> None:
    """Match the current line ``BATCH`` times, then drop what the stub recorded."""
    for _ in range(BATCH):
        harness._eventcb_check_trigger()
    harness.raised.clear()


def _bench_line(
    benchmark: Any, harness: Harness, count: int, text: str, expected: list[str]
) -> None:
    """Load triggers, check what ``text`` raises, then time BATCH matches of it."""
    _loaded(harness, count)
    _set_line(harness, text)
    assert harness.send(text) == expected
    harness.raised.clear()
    _set_line(harness, text)
    benchmark.pedantic(_batch, args=(harness,), rounds=ROUNDS, iterations=1)
    assert harness.raised == []


@pytest.mark.benchmark
@pytest.mark.parametrize("count", SIZES)
def test_bench_trigger_line_no_match(benchmark: Any, harness: Harness, count: int) -> None:
    """Benchmark a line that matches no trigger, in batches of BATCH lines."""
    _bench_line(benchmark, harness, count, NO_MATCH_LINE, [])


@pytest.mark.benchmark
@pytest.mark.parametrize("count", SIZES)
def test_bench_trigger_line_match_first(benchmark: Any, harness: Harness, count: int) -> None:
    """Benchmark a line that matches the first trigger in priority order."""
    _bench_line(benchmark, harness, count, _line_text(0), ["bench0"])


@pytest.mark.benchmark
@pytest.mark.parametrize("count", SIZES)
def test_bench_trigger_line_match_last(benchmark: Any, harness: Harness, count: int) -> None:
    """Benchmark a line that matches the last trigger in priority order."""
    last = count - 1
    _bench_line(benchmark, harness, count, _line_text(last), [f"bench{last}"])


@pytest.mark.benchmark
def test_bench_trigger_add_100(benchmark: Any, monkeypatch: pytest.MonkeyPatch) -> None:
    """Benchmark adding 100 triggers one by one, each round on a fresh harness."""
    harnesses: list[Harness] = []

    def setup() -> tuple[tuple[Harness], dict[str, Any]]:
        fresh = Harness(monkeypatch)
        harnesses.append(fresh)
        return (fresh,), {}

    def add_all(fresh: Harness) -> None:
        for index in range(ADD_COUNT):
            _add_trigger(fresh, index)

    benchmark.pedantic(add_all, setup=setup, rounds=ADD_ROUNDS, iterations=1)
    assert len(harnesses[-1].ordered_names()) == ADD_COUNT
