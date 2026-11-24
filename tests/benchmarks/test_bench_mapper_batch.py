# Project: bastproxy
# Filename: tests/benchmarks/test_bench_mapper_batch.py
#
# File Description: Performance benchmark for the mapper's batch write
#
# By: Bast
"""Performance benchmark for ``map.batch.add`` (#760).

2000 rooms with 5 exits each go in through slices of ``BATCH_LIMIT`` rows, as an
importer sends them. Each slice is one transaction, so the commits stay few.
"""

from pathlib import Path
from typing import Any

import pytest

from bastproxy.plugins.client.mapper.libs._batch import BATCH_LIMIT
from bastproxy.plugins.client.mapper.libs._graph import MapGraph
from bastproxy.plugins.client.mapper.libs._schema import TABLES
from bastproxy.plugins.client.mapper.libs._store import MapStore
from bastproxy.plugins.client.mapper.plugin._mapper import MapperPlugin
from bastproxy.plugins.core.sqldb.libs._sqlite import create_database

OWNER = "plugins.client.mapper"
ROOMS = 2000
EXITS_PER_ROOM = 5
ROWS_PER_ROOM = 1 + EXITS_PER_ROOM
PER_SLICE = BATCH_LIMIT // ROWS_PER_ROOM


def _rooms() -> list[dict[str, Any]]:
    """Build the rooms, each with its embedded exits."""
    return [
        {
            "uid": str(i),
            "name": f"Room {i}",
            "area": "bench",
            "exits": {f"d{n}": str((i + n + 1) % ROOMS) for n in range(EXITS_PER_ROOM)},
        }
        for i in range(ROOMS)
    ]


def _write_all(plugin: Any, rooms: list[dict[str, Any]]) -> None:
    """Send the rooms in slices that stay under the batch limit."""
    for start in range(0, len(rooms), PER_SLICE):
        assert plugin._api_map_batch_add(rooms=rooms[start : start + PER_SLICE]) is not None


@pytest.mark.benchmark
def test_bench_map_batch_add(benchmark: Any, tmp_path: Path) -> None:
    """Benchmark writing 2000 rooms with 5 exits each through map.batch.add."""
    plugin: Any = object.__new__(MapperPlugin)
    plugin.plugin_id = OWNER
    plugin.api = lambda _name: lambda *_a, **_k: None
    db = create_database(OWNER, "map", TABLES, directory=tmp_path)
    plugin.store = MapStore(db)
    plugin.graph = MapGraph()
    rooms = _rooms()
    releases: list[str] = []
    db._conn().set_trace_callback(
        lambda sql: releases.append(sql) if sql.startswith("RELEASE sqldb_0") else None
    )
    benchmark.pedantic(_write_all, args=(plugin, rooms), rounds=1, iterations=1)
    db.close()
    assert len(releases) == -(-ROOMS // PER_SLICE)
    assert len(plugin.graph.snapshot()["rooms"]) == ROOMS
