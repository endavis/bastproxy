# Project: bastproxy
# Filename: tests/benchmarks/test_bench_retention.py
#
# File Description: Benchmark for one MUD to client round with the record store at its cap
#
# By: Bast
"""Benchmark one MUD to client round while the record store is full (#233).

A round is what the proxy does for each message from the MUD. It builds a 15-line
``NetworkData``, wraps it in a ``ProcessDataToClient`` and executes it. Execution raises the
modify event once per line through a real ``Event`` with ``data_list``, which creates the
``EventDataRecord`` and ``ProcessRaisedEvent`` records the live path creates. The store is
filled to ``DEFAULT_MAX_TREES`` root trees before timing starts. Each timed round therefore
adds a tree to a full store and pays its share of the whole-tree eviction (``prune`` runs
once every ``max_trees // 10`` new roots).

Baseline, from audit #106 before #249 (``docs/claude/record_system_findings.md``, Q3): the
store was capped at 5,000 records per type. Evicted lines stayed alive through their holders,
and traced memory grew by about 0.66 MB per round. #249 replaced that with a root-tree cap, so
memory stays flat once the cap is reached. ``tests/libs/records/test_retention.py``
(``test_traced_memory_is_flat_past_the_cap``) checks that; this benchmark times a round at the
cap. It is informational and asserts no target.
"""

from collections.abc import Iterator
from typing import Any

import pytest

from bastproxy.libs.api import API
from bastproxy.libs.records.managers.records import DEFAULT_MAX_TREES, RMANAGER
from bastproxy.libs.records.rtypes.clientdata import ProcessDataToClient
from bastproxy.libs.records.rtypes.networkdata import NetworkData, NetworkDataLine
from bastproxy.libs.records.tracking import tracking_actor
from bastproxy.plugins.core.events.plugin._event import Event

LINES = 15
ROUNDS = 200
OWNER = "bench233"


class _MudToClientRound(ProcessDataToClient):
    """A ProcessDataToClient whose execution raises the modify event over its lines.

    Sending to clients needs a connected client, so the send step is left out.
    """

    modify_event: Event

    def _exec_(self) -> None:
        """Raise the modify event once per line, as ``ProcessDataToClient._exec_`` does."""
        lines = [line for line in self.message if line.frommud and line.is_io]
        self.modify_event.raise_event({}, OWNER, data_list=lines, key_name="line")


@pytest.fixture
def store_at_cap() -> Iterator[None]:
    """Give the benchmark an empty store, then fill it to the default tree cap."""
    saved = (
        RMANAGER.record_instances,
        RMANAGER.records,
        RMANAGER.max_trees,
        RMANAGER._roots_since_prune,
    )
    RMANAGER.record_instances = {}
    RMANAGER.records = {}
    RMANAGER.max_trees = DEFAULT_MAX_TREES
    RMANAGER._roots_since_prune = 0
    api = API(OWNER)
    api.add("plugins.core.settings", "setting.get", lambda *_a, **_k: False, description="stub")
    _MudToClientRound.modify_event = Event("ev_bench233_to_client_modify", created_by=OWNER)
    try:
        for _ in range(DEFAULT_MAX_TREES):
            _run_round(_build_message())
        yield
    finally:
        (
            RMANAGER.record_instances,
            RMANAGER.records,
            RMANAGER.max_trees,
            RMANAGER._roots_since_prune,
        ) = saved
        API._class_api.pop("plugins.core.settings:setting.get", None)


def _build_message() -> NetworkData:
    """Build one message of LINES lines from the MUD."""
    with tracking_actor(OWNER):
        return NetworkData([NetworkDataLine(f"line {i}", originated="mud") for i in range(LINES)])


def _run_round(message: NetworkData) -> _MudToClientRound:
    """Wrap the message in a processing record and execute it."""
    with tracking_actor(OWNER):
        record = _MudToClientRound(message)
        record()
    return record


def _setup_round() -> tuple[tuple[NetworkData], dict[str, Any]]:
    """Per-round setup for ``benchmark.pedantic``: one fresh message, not timed."""
    return (_build_message(),), {}


@pytest.mark.benchmark
@pytest.mark.usefixtures("store_at_cap")
def test_bench_mud_to_client_round_at_cap(benchmark: Any) -> None:
    """Benchmark one 15-line MUD to client round with the store full (informational)."""
    result = benchmark.pedantic(_run_round, setup=_setup_round, rounds=ROUNDS, iterations=1)
    assert not result.executing
    assert RMANAGER.root_count() <= DEFAULT_MAX_TREES + max(1, DEFAULT_MAX_TREES // 10)
