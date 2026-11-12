"""Regression tests for #396: warn about a decorated method with a wrong name."""

# Standard Library
import logging
from typing import Any

# 3rd Party
import pytest

# Project
from bastproxy.plugins.core.commands.plugin._commands import CommandsPlugin

PLUGIN_ID = "plugins.test.fake"


class _Fake:
    plugin_id = "plugins.core.commands"


class _Target:
    plugin_id = PLUGIN_ID

    def _command_good(self) -> None:
        return None

    def wrongname(self) -> None:
        return None

    def plain_helper(self) -> None:
        return None


_Target._command_good.command_data = object()  # type: ignore[attr-defined]
_Target.wrongname.command_data = object()  # type: ignore[attr-defined]


def _get(target: Any) -> list[Any]:
    result: list[Any] = CommandsPlugin.get_command_functions_in_object(_Fake(), target)  # type: ignore[arg-type]
    return result


def test_misnamed_decorated_method_warns_and_is_not_returned(
    caplog: pytest.LogCaptureFixture,
) -> None:
    with caplog.at_level(logging.WARNING):
        found = _get(_Target())
    assert [m.__name__ for m in found] == ["_command_good"]
    warnings = [r.getMessage() for r in caplog.records if r.levelno == logging.WARNING]
    assert len(warnings) == 1
    assert "wrongname" in warnings[0]
    assert PLUGIN_ID in warnings[0]


def test_correct_method_returned_without_warning(caplog: pytest.LogCaptureFixture) -> None:
    class _Good:
        plugin_id = PLUGIN_ID

        def _command_ok(self) -> None:
            return None

    _Good._command_ok.command_data = object()  # type: ignore[attr-defined]
    with caplog.at_level(logging.WARNING):
        found = _get(_Good())
    assert [m.__name__ for m in found] == ["_command_ok"]
    assert not [r for r in caplog.records if r.levelno == logging.WARNING]


def test_undecorated_misnamed_method_does_not_warn(caplog: pytest.LogCaptureFixture) -> None:
    class _Plain:
        plugin_id = PLUGIN_ID

        def helper(self) -> None:
            return None

    with caplog.at_level(logging.WARNING):
        assert _get(_Plain()) == []
    assert not [r for r in caplog.records if r.levelno == logging.WARNING]


def test_same_misnamed_method_reachable_twice_warns_once(
    caplog: pytest.LogCaptureFixture,
) -> None:
    target = _Target()
    holder = _Target()
    holder.alias = target.wrongname  # type: ignore[attr-defined]
    with caplog.at_level(logging.WARNING):
        _get(target)
    warnings = [r for r in caplog.records if r.levelno == logging.WARNING]
    assert len(warnings) == 1
