"""records.children lists the children of an empty record (#686)."""

from collections.abc import Callable
from typing import Any
from unittest.mock import MagicMock

import pytest

from bastproxy.plugins.debug.records.plugin import _records
from bastproxy.plugins.debug.records.plugin._records import RecordPlugin


class _Rec(list[Any]):
    uuid = "r1"


def _run() -> Any:
    stub = MagicMock()

    def api(name: str) -> Callable[..., Any]:
        if name == "plugins.core.commands:command.current.args.get":
            return lambda: {"uid": "r1"}
        raise AssertionError(name)

    stub.api = api
    return RecordPlugin._command_children(stub)


def test_empty_record_children_listed(monkeypatch: pytest.MonkeyPatch) -> None:
    rec = _Rec()
    seen: list[Any] = []
    monkeypatch.setattr(_records.RMANAGER, "get_record", lambda _uid: rec)

    def fmt(record: Any) -> list[str]:
        seen.append(record)
        return ["child line"]

    monkeypatch.setattr(_records.RMANAGER, "format_all_children", fmt)
    result = _run()
    assert result.success is True
    assert result.message == ["child line"]
    assert seen == [rec]


def test_missing_record_not_found(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(_records.RMANAGER, "get_record", lambda _uid: None)
    assert _run().message == ["Record r1 not found"]
