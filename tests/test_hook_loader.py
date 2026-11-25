"""Tests for ``tests/hook_loader.py`` (#1323)."""

from __future__ import annotations

import io
import json
import sys
from typing import TYPE_CHECKING

import pytest
from hook_loader import (
    DANGEROUS_HOOK_PATH,
    load_hook,
    rebound_globals,
    reset_rebound,
    snapshot_rebound,
)

if TYPE_CHECKING:
    from pathlib import Path


def test_rebound_globals_collects_names_from_every_global_statement(tmp_path: Path) -> None:
    source = tmp_path / "two.py"
    source.write_text(
        "def a():\n    global _A\n    _A = 1\n\ndef b():\n    global _B, _C\n    _B = _C = 2\n",
        encoding="utf-8",
    )
    assert rebound_globals(source) == {"_A", "_B", "_C"}


def test_rebound_globals_is_empty_without_global_statements(tmp_path: Path) -> None:
    source = tmp_path / "none.py"
    source.write_text("X = 1\n", encoding="utf-8")
    assert rebound_globals(source) == frozenset()


def test_rebound_globals_finds_payload_cwd_in_the_hook() -> None:
    assert "_PAYLOAD_CWD" in rebound_globals(DANGEROUS_HOOK_PATH)


def test_reset_restores_a_value_main_changed(monkeypatch: pytest.MonkeyPatch) -> None:
    module = load_hook(DANGEROUS_HOOK_PATH, "block_dangerous_commands")
    monkeypatch.setitem(sys.modules, "block_dangerous_commands", module)
    snapshot = snapshot_rebound(module, rebound_globals(DANGEROUS_HOOK_PATH))
    monkeypatch.setattr(module, "get_current_branch", lambda: "feature/test")
    monkeypatch.setattr(module, "_envrc_example_modified", lambda: False)
    payload = {"tool_name": "Bash", "tool_input": {"command": "ls"}, "cwd": "/somewhere"}
    monkeypatch.setattr(sys, "stdin", io.StringIO(json.dumps(payload)))
    module.main()
    assert module._PAYLOAD_CWD is not None
    with pytest.MonkeyPatch.context() as inner:
        reset_rebound(module, snapshot, inner)
        assert module._PAYLOAD_CWD is None


def test_reset_removes_a_function_only_global(tmp_path: Path) -> None:
    source = tmp_path / "fn_only.py"
    source.write_text("def f():\n    global _X\n    _X = 1\n", encoding="utf-8")
    module = load_hook(source, "fn_only_hook")
    snapshot = snapshot_rebound(module, rebound_globals(source))
    module.f()
    assert module._X == 1
    with pytest.MonkeyPatch.context() as inner:
        reset_rebound(module, snapshot, inner)
        assert not hasattr(module, "_X")
