"""Regression tests for #394: re-adding a command must not duplicate commands_list."""

# Standard Library
from types import MethodType

# Local
from .test_add_by_func_bad_placeholder import (
    PLUGIN_ID,
    _add_all,
    _FakeCommands,
    _FakeTarget,
    _make,
    _stub_command_class,
)

__all__ = ["_stub_command_class"]


def test_adding_same_method_twice_leaves_one_entry() -> None:
    target = _FakeTarget()
    fake = _FakeCommands()
    func = _make(target, "_command_aaa")
    _add_all(fake, [func, func])
    assert fake.commands_list == [f"{PLUGIN_ID}.aaa"]


def test_distinct_commands_each_get_an_entry() -> None:
    target = _FakeTarget()
    fake = _FakeCommands()
    funcs: list[MethodType] = [_make(target, "_command_aaa"), _make(target, "_command_bbb")]
    _add_all(fake, funcs)
    assert fake.commands_list == [f"{PLUGIN_ID}.aaa", f"{PLUGIN_ID}.bbb"]


def test_readding_whole_plugin_keeps_entries_unique() -> None:
    target = _FakeTarget()
    fake = _FakeCommands()
    funcs: list[MethodType] = [_make(target, "_command_aaa"), _make(target, "_command_bbb")]
    _add_all(fake, funcs)
    _add_all(fake, funcs)
    assert sorted(fake.commands_list) == [f"{PLUGIN_ID}.aaa", f"{PLUGIN_ID}.bbb"]
