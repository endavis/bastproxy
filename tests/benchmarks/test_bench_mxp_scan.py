# Project: bastproxy
# Filename: tests/benchmarks/test_bench_mxp_scan.py
#
# File Description: Benchmarks for the per-piece MXP scans in mxp_line_mode
#
# By: Bast
"""Benchmark what ``PROTOCOLS.mxp_line_mode`` costs per received piece (#426, area H).

Informational, with no gate. ``mxp_line_mode`` runs ``scan_definitions`` and ``scan_modes`` once
each per piece when MXP is enabled, so this guards the cost of their return shape.

Cases:

1. a batch of 15 plain 77-character lines;
2. a batch of 15 lines carrying a mode escape and tags.
"""

from collections.abc import Iterator
from typing import Any

import pytest

from bastproxy.libs.net.protocols import PROTOCOLS

ROUNDS = 200
LINES = 15
ESC = "\x1b"
PLAIN = "You see a long road that winds north through the hills toward a distant village."
TAGGED = f"{ESC}[1z<!EL a FLAG=x>{ESC}[0z<b>You</b> see a <a href='go north'>road</a> north."


@pytest.fixture
def mxp_state() -> Iterator[None]:
    PROTOCOLS._mxp_reset()
    PROTOCOLS._mxp_defs.clear()
    yield
    PROTOCOLS._mxp_reset()
    PROTOCOLS._mxp_defs.clear()


def _batch(text: str) -> None:
    for _ in range(LINES):
        PROTOCOLS.mxp_line_mode(text, ended=True, enabled=True)


def _reset_defs() -> None:
    PROTOCOLS._mxp_defs.clear()


@pytest.mark.benchmark
@pytest.mark.usefixtures("mxp_state")
def test_bench_mxp_line_mode_plain(benchmark: Any) -> None:
    """Benchmark a 15 line batch of plain lines."""
    benchmark.pedantic(_batch, args=(PLAIN,), setup=_reset_defs, rounds=ROUNDS, iterations=1)


@pytest.mark.benchmark
@pytest.mark.usefixtures("mxp_state")
def test_bench_mxp_line_mode_tagged(benchmark: Any) -> None:
    """Benchmark a 15 line batch of lines with a mode escape and tags."""
    benchmark.pedantic(_batch, args=(TAGGED,), setup=_reset_defs, rounds=ROUNDS, iterations=1)
