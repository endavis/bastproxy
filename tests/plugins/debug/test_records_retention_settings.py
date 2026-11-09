"""The records plugin owns the retention settings (#249, #233)."""

from collections.abc import Callable, Iterator
from typing import Any

import pytest

from bastproxy.libs.records import RMANAGER
from bastproxy.plugins.debug.records.plugin import _records
from bastproxy.plugins.debug.records.plugin._records import RecordPlugin


class _StubPlugin:
    plugin_id = "plugins.debug.records"

    def __init__(self, newvalue: Any = None) -> None:
        self.api = _StubApi(newvalue)
        self._apply_retained_trees = lambda value: RecordPlugin._apply_retained_trees(
            self,  # type: ignore[arg-type]
            value,
        )
        self._apply_tracking_max_changes = lambda value: RecordPlugin._apply_tracking_max_changes(
            self,  # type: ignore[arg-type]
            value,
        )


class _StubApi:
    def __init__(self, newvalue: Any) -> None:
        self.newvalue = newvalue

    def __call__(self, name: str) -> Callable[..., Any]:
        if name.endswith("event.current.record.get"):
            return lambda: {"newvalue": self.newvalue}
        raise AssertionError(name)


@pytest.fixture(autouse=True)
def _restore(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    monkeypatch.setattr(RMANAGER, "max_trees", RMANAGER.max_trees)
    monkeypatch.setattr(RMANAGER, "max_changes", RMANAGER.max_changes)
    yield


def test_apply_retained_trees_sets_the_manager() -> None:
    RecordPlugin._apply_retained_trees(_StubPlugin(), "7")  # type: ignore[arg-type]
    assert RMANAGER.max_trees == 7


def test_apply_none_is_a_no_op() -> None:
    RMANAGER.max_trees = 9
    RMANAGER.max_changes = 11
    RecordPlugin._apply_retained_trees(_StubPlugin(), None)  # type: ignore[arg-type]
    RecordPlugin._apply_tracking_max_changes(_StubPlugin(), None)  # type: ignore[arg-type]
    assert (RMANAGER.max_trees, RMANAGER.max_changes) == (9, 11)


def test_apply_tracking_max_changes_sets_the_manager() -> None:
    RecordPlugin._apply_tracking_max_changes(_StubPlugin(), "12")  # type: ignore[arg-type]
    assert RMANAGER.max_changes == 12


def test_modified_callbacks_apply_the_new_value() -> None:
    stub = _StubPlugin(33)
    RecordPlugin._eventcb_retained_trees_modified(stub)
    assert RMANAGER.max_trees == 33
    stub = _StubPlugin(44)
    RecordPlugin._eventcb_tracking_max_changes_modified(stub)
    assert RMANAGER.max_changes == 44


def test_types_output_starts_with_the_tree_header() -> None:
    ok, lines = RecordPlugin._command_types(_StubPlugin())
    assert ok
    assert lines[0] == f"Root trees: {RMANAGER.root_count()} (retaining {RMANAGER.max_trees})"
    assert lines[1] == "Record Types:"
    assert _records.RMANAGER is RMANAGER
