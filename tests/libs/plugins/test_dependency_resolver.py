# Project: bastproxy
# Filename: tests/libs/plugins/test_dependency_resolver.py
#
# File Description: Pure tests for PluginDependencyResolver
#
# By: Bast
"""Tests for ``PluginDependencyResolver`` (issue #97)."""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

from bastproxy.libs.exceptions import PluginDependencyError
from bastproxy.libs.plugins.dependency import (
    CircularDependencyError,
    PluginDependencyResolver,
)


def _infos(graph: dict[str, list[str]]) -> dict[str, Any]:
    return {pid: SimpleNamespace(plugin_id=pid, dependencies=deps) for pid, deps in graph.items()}


def test_dependencies_come_first_and_input_order_is_kept() -> None:
    infos = _infos({"a": [], "b": ["a"], "c": [], "d": ["c"]})
    result = PluginDependencyResolver(infos).resolve(["d", "b", "c", "a"])
    assert result.failed == {}
    assert result.order == ["c", "d", "a", "b"]


def test_unlisted_dependency_is_pulled_in() -> None:
    infos = _infos({"a": [], "b": ["a"]})
    result = PluginDependencyResolver(infos).resolve(["b"])
    assert result.order == ["a", "b"]
    assert result.failed == {}


def test_loaded_dependency_is_not_pulled_in() -> None:
    infos = _infos({"a": [], "b": ["a"]})
    result = PluginDependencyResolver(infos, loaded=["a"]).resolve(["b"])
    assert result.order == ["b"]
    assert result.failed == {}


def test_missing_dependency_fails_dependents_transitively() -> None:
    infos = _infos({"a": ["nope"], "b": ["a"], "c": []})
    result = PluginDependencyResolver(infos).resolve(["a", "b", "c"])
    assert result.order == ["c"]
    assert set(result.failed) == {"nope", "a", "b"}
    assert "does not exist" in str(result.failed["nope"])
    assert "nope" in str(result.failed["a"])


def test_two_node_cycle_fails_only_cycle_and_dependents() -> None:
    infos = _infos({"a": ["b"], "b": ["a"], "d": ["a"], "ok": []})
    result = PluginDependencyResolver(infos).resolve(["a", "b", "d", "ok"])
    assert result.order == ["ok"]
    assert set(result.failed) == {"a", "b", "d"}
    err = result.failed["a"]
    assert isinstance(err, CircularDependencyError)
    assert isinstance(err, PluginDependencyError)
    assert err.cycle == ["a", "b", "a"]
    assert "a -> b -> a" in str(err)
    assert not isinstance(result.failed["d"], CircularDependencyError)


def test_three_node_cycle_path_is_reported() -> None:
    infos = _infos({"a": ["b"], "b": ["c"], "c": ["a"], "ok": []})
    result = PluginDependencyResolver(infos).resolve(["a", "ok"])
    assert result.order == ["ok"]
    err = result.failed["a"]
    assert isinstance(err, CircularDependencyError)
    assert "a -> b -> c -> a" in str(err)
    assert set(result.failed) == {"a", "b", "c"}


def test_dependents_of_is_transitive_and_nearest_first() -> None:
    infos = _infos({"a": [], "b": ["a"], "c": ["b"], "d": ["a"], "x": []})
    resolver = PluginDependencyResolver(infos)
    assert resolver.dependents_of("a", ["a", "b", "c", "d", "x"]) == ["b", "d", "c"]
    assert resolver.dependents_of("a", ["x", "c"]) == []
    assert resolver.dependents_of("x", ["a", "b", "c"]) == []
