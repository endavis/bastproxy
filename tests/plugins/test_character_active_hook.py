"""The character_active plugin hook runs from the after-character-active callback (#589)."""

from typing import Any
from unittest.mock import MagicMock

from bastproxy.plugins._baseplugin import BasePlugin, RegisterPluginHook


class _Stub(BasePlugin):
    """A BasePlugin that skips __init__ and keeps only the test hooks."""

    def __init__(self, connected: bool = False, active: bool = False) -> None:
        self.plugin_id = "plugins.test.character_active_stub"
        self.is_character_active_priority = None
        self.calls: list[str] = []
        self.registered: list[tuple[str, Any]] = []
        self.unregistered: list[tuple[str, Any]] = []
        self.is_registered = False

        def register(name: str, func: Any, **_k: Any) -> None:
            self.registered.append((name, func))
            self.is_registered = True

        def unregister(name: str, func: Any) -> None:
            self.unregistered.append((name, func))
            self.is_registered = False

        funcs: dict[str, Any] = {
            "plugins.core.events:event.register": register,
            "plugins.core.events:event.unregister": unregister,
            "plugins.core.events:event.is.registered": lambda *_a: self.is_registered,
            "plugins.core.proxy:mud.is.connected": lambda: connected,
            "libs.api:character.is.active": lambda: active,
        }
        self.api = MagicMock(side_effect=lambda name: funcs.get(name, MagicMock()))

    def _get_plugin_hook_functions(self, obj: Any, plugin_hook: Any, recurse: Any = True) -> dict:
        functions = super()._get_plugin_hook_functions(obj, plugin_hook, recurse)
        return {
            prio: [f for f in funcs if f.__name__.startswith("_phook_stub_")]
            for prio, funcs in functions.items()
        }

    @RegisterPluginHook("character_active", priority=70)
    def _phook_stub_last(self) -> None:
        self.calls.append("last")

    @RegisterPluginHook("character_active", priority=10)
    def _phook_stub_first(self) -> None:
        self.calls.append("first")

    @RegisterPluginHook("character_active")
    def _phook_stub_middle(self) -> None:
        self.calls.append("middle")


def test_hooks_run_once_on_activation_in_priority_order() -> None:
    stub = _Stub()
    stub._eventcb_baseplugin_after_character_is_active()
    assert stub.calls == ["first", "middle", "last"]


def test_hooks_run_at_load_when_connected_and_active() -> None:
    stub = _Stub(connected=True, active=True)
    stub._phook_base_post_initialize_setup()
    assert stub.calls == ["first", "middle", "last"]
    assert stub.registered == []


def test_hooks_wait_at_load_when_not_active() -> None:
    stub = _Stub(connected=True, active=False)
    stub._phook_base_post_initialize_setup()
    assert stub.calls == []
    assert [name for name, _ in stub.registered] == ["ev_libs.api_character_active"]


def test_hooks_run_once_per_login() -> None:
    stub = _Stub(connected=True, active=False)
    stub._phook_base_post_initialize_setup()
    stub._eventcb_baseplugin_after_character_is_active()
    assert len(stub.calls) == 3
    assert stub.is_registered is False

    stub._eventcb_baseplugin_disconnect()
    assert stub.is_registered is True
    stub._eventcb_baseplugin_after_character_is_active()
    assert len(stub.calls) == 6
    assert stub.is_registered is False


def test_override_calling_super_still_works() -> None:
    class _Override(_Stub):
        def _eventcb_baseplugin_after_character_is_active(self) -> None:
            self.calls.append("override")
            super()._eventcb_baseplugin_after_character_is_active()

    stub = _Override()
    stub._eventcb_baseplugin_after_character_is_active()
    assert stub.calls == ["override", "first", "middle", "last"]


def test_override_without_hooks_does_not_need_them() -> None:
    class _Plain(BasePlugin):
        def __init__(self) -> None:
            self.plugin_id = "plugins.test.plain"
            self.api = MagicMock()

    plain = _Plain()
    plain._eventcb_baseplugin_after_character_is_active()
