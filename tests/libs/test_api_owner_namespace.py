"""Owner IDs share one namespace with API toplevels and resolve for library APIs (#202).

Test Classes:
    - `TestLibraryToplevels`: library toplevels carry no `bastproxy.` prefix.
    - `TestFunctionOwnerGet`: `function.owner.get` and its registered-owner fallback.
    - `TestNoPrefixStrip`: the `bastproxy.` strips are gone from the API.
    - `TestStaticOwnerGuard`: no owner ID is built from `__name__`.
    - `TestPostStartupEvent`: the public event name is unchanged.

"""

from __future__ import annotations

import ast
from collections.abc import Iterator
from pathlib import Path

import pytest

from bastproxy.libs import timing  # noqa: F401  (registers its toplevel)
from bastproxy.libs.api import API
from bastproxy.libs.api._apistats import STATS_MANAGER
from bastproxy.libs.exceptions import APINotFoundError
from bastproxy.libs.plugins import (
    loader,
    reloadutils,  # noqa: F401  (registers its toplevel)
)
from bastproxy.libs.plugins.loader import PluginLoader

# registered once at import: the per-test isolation fixture restores the registry,
# and a toplevel is only added once per function
_LOADER = PluginLoader()

SRC = Path(__file__).resolve().parents[2] / "src" / "bastproxy"


@pytest.fixture(autouse=True)
def _isolate_api_state() -> Iterator[None]:
    """Restore the shared class API registry and stats after every test."""
    class_api_snapshot = dict(API._class_api)
    stats_snapshot = dict(STATS_MANAGER.stats)
    yield
    API._class_api.clear()
    API._class_api.update(class_api_snapshot)
    STATS_MANAGER.stats.clear()
    STATS_MANAGER.stats.update(stats_snapshot)


class _Plugin:
    """Object with a plugin_id."""

    plugin_id = "my_plugin"

    def method(self) -> None:
        """Bound method."""


class _OwnerOnly:
    """Object with only an owner_id."""

    owner_id = "only_owner"

    def method(self) -> None:
        """Bound method."""


def _unregistered() -> None:
    """Function that is never registered."""


class TestLibraryToplevels:
    """Library toplevels use the module path under bastproxy."""

    def test_module_toplevels_have_matching_owner(self) -> None:
        """Timing, reloadutils and the loader register unprefixed toplevels."""
        for name, owner in (
            ("libs.timing:timing.toggle", "libs.timing"),
            ("libs.plugins.reloadutils:cache.add", "libs.plugins.reloadutils"),
            ("libs.plugins.loader:plugin.list", "libs.plugins.loader"),
        ):
            assert name in API._class_api
            assert API._class_api[name].owner_id == owner

    def test_no_prefixed_keys_or_owners(self) -> None:
        """No class API key or owner starts with bastproxy."""
        for key, item in API._class_api.items():
            assert not key.startswith("bastproxy.")
            assert not (item.owner_id or "").startswith("bastproxy.")


class TestFunctionOwnerGet:
    """Behaviour of `function.owner.get`."""

    def test_loader_function_resolves_to_library_owner(self) -> None:
        """The loader's plugin.list resolves to libs.plugins.loader."""
        api = API(owner_id="test_owner_ns")
        registered = API._class_api["libs.plugins.loader:plugin.list"].tfunction
        assert api._api_function_owner_get(registered) == "libs.plugins.loader"

    def test_plugin_id_wins_over_registration(self) -> None:
        """A bound method with plugin_id returns it even if registered elsewhere."""
        api = API(owner_id="libs.fake")
        obj = _Plugin()
        api("libs.api:api.add")("libs.fake", "thing", obj.method)
        assert api._api_function_owner_get(obj.method) == "my_plugin"

    def test_unregistered_function_is_unknown(self) -> None:
        """An unregistered function has no owner."""
        api = API(owner_id="libs.fake")
        assert api._api_function_owner_get(_unregistered) == "unknown"

    def test_owner_id_only_object_is_unknown(self) -> None:
        """A bound method with only owner_id, unregistered, is unknown."""
        api = API(owner_id="libs.fake")
        assert api._api_function_owner_get(_OwnerOnly().method) == "unknown"

    def test_registered_function_returns_owner(self) -> None:
        """A function registered with api.add returns the registering owner."""
        api = API(owner_id="libs.fake")
        api("libs.api:api.add")("libs.fake", "func", _unregistered)
        assert api._api_function_owner_get(_unregistered) == "libs.fake"


class TestNoPrefixStrip:
    """The `bastproxy.` strips were removed."""

    def test_add_for_object_keeps_prefixed_toplevel(self) -> None:
        """api.add.for.object keeps a bastproxy.fake toplevel verbatim."""
        from bastproxy.libs.api import AddAPI

        class Thing:
            @AddAPI("thing.do", description="do")
            def _api_thing_do(self) -> None:
                """Do."""

        api = API(owner_id="bastproxy.x")
        api("libs.api:api.add.for.object")("bastproxy.fake", Thing())
        assert "bastproxy.fake:thing.do" in API._class_api

    def test_get_does_not_strip_prefix(self) -> None:
        """A bastproxy.-prefixed lookup no longer resolves."""
        api = API(owner_id="bastproxy.x")
        with pytest.raises(APINotFoundError):
            api.get("bastproxy.libs.plugins.loader:plugin.list")


def _owner_exprs(tree: ast.AST) -> Iterator[ast.expr]:
    """Yield expressions that become API owner IDs or toplevels."""
    for node in ast.walk(tree):
        if isinstance(node, ast.keyword) and node.arg == "owner_id":
            yield node.value
        elif isinstance(node, ast.Call):
            func = node.func
            if isinstance(func, ast.Call) and node.args:
                inner = func.args[0] if func.args else None
                if isinstance(inner, ast.Constant) and inner.value == "libs.api:api.add.for.object":
                    yield node.args[0]
                elif isinstance(func.func, ast.Attribute) and func.func.attr == "api":
                    yield func.args[0]


def _uses_dunder_name(expr: ast.expr) -> bool:
    return any(isinstance(n, ast.Name) and n.id == "__name__" for n in ast.walk(expr))


class TestStaticOwnerGuard:
    """No API owner or toplevel is derived from ``__name__``."""

    def test_no_owner_built_from_dunder_name(self) -> None:
        """Scan src for owner_id=, api.add.for.object and self.api(...) uses."""
        offenders: list[str] = []
        for path in SRC.rglob("*.py"):
            tree = ast.parse(path.read_text(encoding="utf-8"))
            for expr in _owner_exprs(tree):
                if _uses_dunder_name(expr):
                    offenders.append(f"{path.relative_to(SRC)}:{expr.lineno}")
        assert offenders == []


class TestPostStartupEvent:
    """The public event name is unchanged."""

    def test_event_name_is_unchanged(self) -> None:
        """POST_STARTUP_EVENT keeps its historical value."""
        assert (
            loader.POST_STARTUP_EVENT
            == "ev_bastproxy.libs.plugins.loader_post_startup_plugins_loaded"
        )
