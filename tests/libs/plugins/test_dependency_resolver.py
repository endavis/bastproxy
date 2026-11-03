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
    order, failed = PluginDependencyResolver(infos).resolve(["d", "b", "c", "a"])
    assert failed == {}
    assert order == ["c", "d", "a", "b"]


def test_unlisted_dependency_is_pulled_in() -> None:
    infos = _infos({"a": [], "b": ["a"]})
    order, failed = PluginDependencyResolver(infos).resolve(["b"])
    assert order == ["a", "b"]
    assert failed == {}


def test_loaded_dependency_is_not_pulled_in() -> None:
    infos = _infos({"a": [], "b": ["a"]})
    order, failed = PluginDependencyResolver(infos, loaded=["a"]).resolve(["b"])
    assert order == ["b"]
    assert failed == {}


def test_missing_dependency_fails_dependents_transitively() -> None:
    infos = _infos({"a": ["nope"], "b": ["a"], "c": []})
    order, failed = PluginDependencyResolver(infos).resolve(["a", "b", "c"])
    assert order == ["c"]
    assert set(failed) == {"nope", "a", "b"}
    assert "does not exist" in str(failed["nope"])
    assert "nope" in str(failed["a"])


def test_two_node_cycle_fails_only_cycle_and_dependents() -> None:
    infos = _infos({"a": ["b"], "b": ["a"], "d": ["a"], "ok": []})
    order, failed = PluginDependencyResolver(infos).resolve(["a", "b", "d", "ok"])
    assert order == ["ok"]
    assert set(failed) == {"a", "b", "d"}
    err = failed["a"]
    assert isinstance(err, CircularDependencyError)
    assert isinstance(err, PluginDependencyError)
    assert err.cycle == ["a", "b", "a"]
    assert "a -> b -> a" in str(err)
    assert not isinstance(failed["d"], CircularDependencyError)


def test_three_node_cycle_path_is_reported() -> None:
    infos = _infos({"a": ["b"], "b": ["c"], "c": ["a"], "ok": []})
    order, failed = PluginDependencyResolver(infos).resolve(["a", "ok"])
    assert order == ["ok"]
    err = failed["a"]
    assert isinstance(err, CircularDependencyError)
    assert "a -> b -> c -> a" in str(err)
    assert set(failed) == {"a", "b", "c"}


def test_dependents_of_is_transitive_and_nearest_first() -> None:
    infos = _infos({"a": [], "b": ["a"], "c": ["b"], "d": ["a"], "x": []})
    resolver = PluginDependencyResolver(infos)
    assert resolver.dependents_of("a", ["a", "b", "c", "d", "x"]) == ["b", "d", "c"]
    assert resolver.dependents_of("a", ["x", "c"]) == []
    assert resolver.dependents_of("x", ["a", "b", "c"]) == []
