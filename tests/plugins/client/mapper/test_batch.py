"""Tests for the batch merge and validation helpers."""

from typing import Any

from bastproxy.plugins.client.mapper.libs._batch import (
    BAD_EXIT,
    BAD_REQUIREMENT,
    BatchResult,
    count_rows,
    exit_problem,
    merge_exit,
    merge_room,
    normalize_room,
)
from bastproxy.plugins.client.mapper.libs._graph import Exit


def test_merge_exit_new_exit_is_written() -> None:
    given = Exit("A", "n", "B", 2, None)
    assert merge_exit(None, given, True) == given
    assert merge_exit(None, given, False) == given


def test_merge_exit_unknown_touid_never_replaces_known() -> None:
    stored = Exit("A", "n", "B", 1, None)
    given = Exit("A", "n", "-1", 4, {"x": 1})
    merged = merge_exit(stored, given, True)
    assert merged == Exit("A", "n", "B", 4, {"x": 1})
    assert merge_exit(stored, Exit("A", "n", "-1", 1, None), True) is None


def test_merge_exit_overwrite_replaces_cost_and_requirement() -> None:
    stored = Exit("A", "n", "B", 1, {"a": 1})
    assert merge_exit(stored, Exit("A", "n", "C", 7, None), True) == Exit("A", "n", "C", 7, None)


def test_merge_exit_fill_keeps_cost_and_fills_gaps() -> None:
    stored = Exit("A", "n", "-1", 3, None)
    given = Exit("A", "n", "B", 9, {"r": 1})
    assert merge_exit(stored, given, False) == Exit("A", "n", "B", 3, {"r": 1})
    known = Exit("A", "n", "C", 3, {"k": 1})
    assert merge_exit(known, given, False) is None


def test_merge_room_overwrite_and_new() -> None:
    given = normalize_room({"uid": 1, "name": "N", "flags": ["a"]})
    assert given is not None
    assert merge_room(None, given, False) == given
    stored = {**given, "name": "old"}
    assert merge_room(stored, given, True) == given
    assert merge_room(given, given, True) is None


def test_merge_room_fill_appends_only_missing_flags() -> None:
    given = normalize_room({"uid": "1", "name": "new", "area": "z", "flags": ["a", "b", "b"]})
    assert given is not None
    stored: dict[str, Any] = {**given, "name": "old", "area": "keep", "flags": ["a"]}
    merged = merge_room(stored, given, False)
    assert merged is not None
    assert merged["name"] == "old"
    assert merged["area"] == "keep"
    assert merged["flags"] == ["a", "b"]
    assert merge_room(merged, given, False) is None


def test_normalize_room_needs_a_uid() -> None:
    assert normalize_room({"name": "x"}) is None
    assert normalize_room({"uid": ""}) is None
    assert normalize_room("nope") is None
    room = normalize_room({"uid": 5})
    assert room is not None
    assert room["uid"] == "5"
    assert room["flags"] == []


def test_exit_problem() -> None:
    assert exit_problem("A", "n", 1, None) is None
    assert exit_problem("", "n", 1, None) == BAD_EXIT
    assert exit_problem("A", "", 1, None) == BAD_EXIT
    assert exit_problem("A", "n", -1, None) == BAD_EXIT
    assert exit_problem("A", "n", "1", None) == BAD_EXIT
    assert exit_problem("A", "n", 1, object()) == BAD_REQUIREMENT


def test_count_rows_counts_embedded_exits() -> None:
    rooms = [{"uid": "1", "exits": {"n": "2", "s": "3"}}, {"uid": "2"}]
    assert count_rows([{"uid": "a"}], rooms, [{"fromuid": "1"}], {"1": "x"}) == 7
    assert count_rows(None, None, None, None) == 0


def test_batch_result_counts_and_changed() -> None:
    result = BatchResult()
    assert result.changed() is False
    result.notes = 1
    assert result.changed() is True
    assert result.counts()["notes"] == 1


def test_merge_exit_keep_details_overwrite() -> None:
    """keep_details with overwrite keeps cost and requirement, and updates the touid (#762)."""
    stored = Exit("A", "n", "B", 3, {"level": 100})
    assert merge_exit(stored, Exit("A", "n", "C"), True, keep_details=True) == Exit(
        "A", "n", "C", 3, {"level": 100}
    )
    assert merge_exit(stored, Exit("A", "n", "-1"), True, keep_details=True) is None
    assert merge_exit(None, Exit("A", "n", "C"), True, keep_details=True) == Exit("A", "n", "C")
    # fill mode is unchanged by the flag
    given = Exit("A", "n", "C", 9, {"x": 1})
    assert merge_exit(stored, given, False, keep_details=True) == merge_exit(stored, given, False)
