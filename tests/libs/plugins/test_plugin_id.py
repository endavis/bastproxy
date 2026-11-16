# Project: bastproxy
# Filename: tests/libs/plugins/test_plugin_id.py
#
# File Description: Tests for the PluginId value type
#
# By: Bast
"""Tests for ``PluginId`` and its adoption by ``PluginInfo`` and discovery (issue #436)."""

from __future__ import annotations

import copy
import json
import pickle
from pathlib import Path
from typing import Any

import pytest

from bastproxy.libs.plugins.pluginid import PluginId
from bastproxy.libs.plugins.plugininfo import PluginInfo

RAW = "plugins.core.commands"


def test_parts() -> None:
    """``package`` and ``plugin`` split on the last dot."""
    pid = PluginId(RAW)
    assert pid.package == "plugins.core"
    assert pid.plugin == "commands"
    deep = PluginId("plugins.user.sub.x")
    assert deep.package == "plugins.user.sub"
    assert deep.plugin == "x"


def test_is_str_without_dict() -> None:
    """It is a ``str`` and carries no per-instance ``__dict__``."""
    pid = PluginId(RAW)
    assert isinstance(pid, str)
    assert not hasattr(pid, "__dict__")


def test_eq_and_hash_parity() -> None:
    """Equality and hash match the plain string, in both directions."""
    pid = PluginId(RAW)
    assert pid == RAW
    assert RAW == pid  # noqa: SIM300  # the str-on-the-left comparison is what is tested
    assert hash(pid) == hash(RAW)
    assert pid != PluginId("plugins.core.api")


def test_dict_and_set_lookup() -> None:
    """Dict and set lookups work with either type."""
    pid = PluginId(RAW)
    assert {RAW: 1}[pid] == 1
    by_id: dict[Any, int] = {pid: 2}
    assert by_id[RAW] == 2
    assert RAW in {pid}
    assert pid in {RAW}


def test_formatting_and_json() -> None:
    """JSON, ``str()``, f-strings and ``repr`` match the plain string."""
    pid = PluginId(RAW)
    assert json.dumps({"id": pid}) == json.dumps({"id": RAW})
    assert type(str(pid)) is str
    assert type(f"{pid}") is str
    assert f"{pid}" == RAW
    assert f"libs.plugins.loader:{pid}.x" == f"libs.plugins.loader:{RAW}.x"
    assert repr(pid) == repr(RAW)


def test_string_behaviour() -> None:
    """String methods, sorting, pickling and paths keep working."""
    pid = PluginId(RAW)
    assert pid.startswith("plugins.")
    parts = pid.split(".")
    assert parts == ["plugins", "core", "commands"]
    assert all(type(x) is str for x in parts)
    mixed: list[Any] = [PluginId("plugins.b.x"), "plugins.a.x", PluginId("plugins.c.x")]
    assert sorted(mixed) == ["plugins.a.x", "plugins.b.x", "plugins.c.x"]
    for clone in (pickle.loads(pickle.dumps(pid)), copy.deepcopy(pid)):
        assert clone == pid
        assert isinstance(clone, PluginId)
    assert Path("base") / pid == Path("base") / RAW


def test_idempotent_and_from_parts() -> None:
    """Wrapping an id is a no-op in value; ``from_parts`` joins with a dot."""
    pid = PluginId(RAW)
    assert PluginId(pid) == pid
    built = PluginId.from_parts("plugins.core", "commands")
    assert built == pid
    assert built.package == "plugins.core"


@pytest.mark.parametrize("bad", ["commands", "", ".commands", "plugins."])
def test_invalid_value(bad: str) -> None:
    """A string that is not ``<package>.<plugin>`` raises ``ValueError``."""
    with pytest.raises(ValueError, match="invalid plugin id"):
        PluginId(bad)


@pytest.mark.parametrize("bad", [None, 1])
def test_invalid_type(bad: Any) -> None:
    """A non-str raises ``TypeError``."""
    with pytest.raises(TypeError):
        PluginId(bad)


def test_plugininfo_uses_plugin_id() -> None:
    """``PluginInfo`` stores a ``PluginId`` and derives its parts from it."""
    info = PluginInfo(RAW)
    assert type(info.plugin_id) is PluginId
    assert info.plugin_id == RAW
    assert info.package == "plugins.core"
    assert info.short_name == "commands"
    assert info.is_dev is False
    assert PluginInfo("plugins.core._base").is_dev is True
