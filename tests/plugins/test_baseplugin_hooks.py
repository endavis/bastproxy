"""Tests for plugin hook lookup in the base plugin (#126)."""

from typing import Any

from bastproxy.plugins._baseplugin import RegisterPluginHook
from bastproxy.plugins._baseplugin._base import Plugin


class _Hooked(Plugin):
    """A plugin stub with hooks, skipping Plugin.__init__."""

    def __init__(self) -> None:
        pass

    @RegisterPluginHook("t126", priority=50)
    def _phook_b(self) -> None:
        pass

    @RegisterPluginHook("t126", priority=50)
    def _phook_a(self) -> None:
        pass

    @RegisterPluginHook("t126", priority=10)
    def _phook_z(self) -> None:
        pass

    @RegisterPluginHook("t126", priority=90)
    @RegisterPluginHook("t126b", priority=5)
    def _phook_multi(self) -> None:
        pass

    @RegisterPluginHook("t126", priority=1)
    def not_prefixed(self) -> None:
        pass


def _names(funcs: list[Any]) -> list[str]:
    return [f.__name__ for f in funcs]


def test_same_priority_hooks_all_listed() -> None:
    """Both hooks at priority 50 appear in get.plugin.hooks."""
    hooks = _Hooked()._api_get_plugin_hooks()
    assert set(_names(hooks["t126"][50])) == {"_phook_a", "_phook_b"}


def test_priority_order_ascending() -> None:
    """Priorities come out lowest first."""
    hooks = _Hooked()._api_get_plugin_hooks()
    assert list(hooks["t126"]) == [10, 50, 90]


def test_tie_order_is_alphabetical_and_stable() -> None:
    """Ties keep method-name order, identically on every call."""
    plugin = _Hooked()
    for _ in range(3):
        assert _names(plugin._api_get_plugin_hooks()["t126"][50]) == [
            "_phook_a",
            "_phook_b",
        ]


def test_unprefixed_method_ignored() -> None:
    """A method without the _phook_ prefix never runs, so it is not listed."""
    hooks = _Hooked()._api_get_plugin_hooks()
    assert 1 not in hooks["t126"]


def test_get_plugin_hooks_matches_run_list() -> None:
    """get.plugin.hooks lists what _get_plugin_hook_functions runs."""
    plugin = _Hooked()
    all_hooks = plugin._api_get_plugin_hooks()
    assert {"t126", "t126b"} <= set(all_hooks)
    assert "__init__" in all_hooks  # base plugin hooks are listed too
    for hook, expected in all_hooks.items():
        run = plugin._get_plugin_hook_functions(plugin, hook)
        assert run == expected
        assert list(run) == sorted(run)


def test_unknown_hook_returns_empty() -> None:
    """A hook nobody registered gives an empty run list."""
    plugin = _Hooked()
    assert plugin._get_plugin_hook_functions(plugin, "nope") == {}
