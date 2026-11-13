"""The plugin hook run by BasePlugin.initialize() is named after_load (#423)."""

import re
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

import pytest

from bastproxy.plugins._baseplugin import BasePlugin, RegisterPluginHook

SRC = Path(__file__).resolve().parents[2] / "src" / "bastproxy"


def test_no_initialize_hook_registered_in_src() -> None:
    pattern = re.compile(r"RegisterPluginHook\(\s*[\"']initialize[\"']")
    offenders = [
        str(path.relative_to(SRC))
        for path in SRC.rglob("*.py")
        if pattern.search(path.read_text(encoding="utf-8"))
    ]
    assert offenders == []


def test_initialize_does_not_process_the_initialize_hook() -> None:
    source = (SRC / "plugins" / "_baseplugin" / "_base.py").read_text(encoding="utf-8")
    assert '_process_plugin_hook("initialize")' not in source
    assert '_process_plugin_hook("after_load")' in source


class _Stub(BasePlugin):
    """A BasePlugin that skips __init__ and keeps only the test hooks."""

    def __init__(self) -> None:
        self.plugin_id = "plugins.test.after_load_stub"
        self.api = MagicMock()
        self.calls: list[str] = []

    def _get_plugin_hook_functions(self, obj: Any, plugin_hook: Any, recurse: Any = True) -> dict:
        functions = super()._get_plugin_hook_functions(obj, plugin_hook, recurse)
        # Keep only this stub's own hooks, not the base class's.
        return {
            prio: [f for f in funcs if f.__name__.startswith("_phook_stub_")]
            for prio, funcs in functions.items()
        }

    @RegisterPluginHook("after_load")
    def _phook_stub_after_load(self) -> None:
        self.calls.append("after_load")


def test_initialize_runs_after_load_hooks_only() -> None:
    stub = _Stub()
    stub.initialize()
    assert stub.calls == ["after_load"]


def test_registering_the_old_initialize_name_raises() -> None:
    with pytest.raises(ValueError, match="after_load"):
        RegisterPluginHook("initialize")
