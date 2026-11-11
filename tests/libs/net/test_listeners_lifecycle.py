"""Tests for Listeners settings reset, listener creation and retry (#310)."""

import asyncio
import logging
from collections.abc import Callable, Coroutine
from typing import Any

import pytest

from bastproxy.libs.net import client as net_client
from bastproxy.libs.net import listeners as listeners_mod
from bastproxy.libs.net.listeners import Listeners


class FakeTask:
    """Stand-in for TaskItem with the same done/result properties."""

    def __init__(self, error: Exception | None = None) -> None:
        self.done = True
        self._error = error

    @property
    def result(self) -> None:
        if self._error:
            raise self._error


class Env:
    """A Listeners object whose settings and task creation are recorded."""

    def __init__(self, monkeypatch: pytest.MonkeyPatch, **settings: Any) -> None:
        self.settings: dict[str, Any] = {
            "ipv4": True,
            "ipv6": False,
            "ipv4address": "127.0.0.1",
            "ipv6address": "::1",
            "listenport": 9999,
            **settings,
        }
        self.sets: list[tuple[str, Any]] = []
        self.added: list[tuple[Any, str]] = []
        self.server_calls: list[dict[str, Any]] = []
        self.task_factory: Callable[[str], Any] = lambda name: FakeTask()

        async def no_sleep(_delay: float) -> None:
            return None

        monkeypatch.setattr(listeners_mod.asyncio, "sleep", no_sleep)

        def create_server(**kwargs: Any) -> str:
            self.server_calls.append(kwargs)
            return f"server:{kwargs['host']}"

        monkeypatch.setattr(listeners_mod.server, "create_server", create_server)
        self.obj = Listeners()
        self.obj.api = self._api  # type: ignore[assignment]

    def _api(self, name: str) -> Callable[..., Any]:
        if name == "plugins.core.settings:setting.get":
            return lambda _plugin, key: self.settings[key]
        if name == "plugins.core.settings:setting.set":

            def set_(_plugin: str, key: str, value: Any) -> None:
                self.sets.append((key, value))
                if value != "default":
                    self.settings[key] = value

            return set_
        if name == "libs.asynch:task.add":

            def add(obj: Any, taskname: str, **_kwargs: Any) -> Any:
                self.added.append((obj, taskname))
                if isinstance(obj, Coroutine):
                    obj.close()
                return self.task_factory(taskname)

            return add
        raise AssertionError(name)


def test_reset_listener_settings_sets_every_key_to_default(monkeypatch: pytest.MonkeyPatch) -> None:
    env = Env(monkeypatch)
    env.obj.reset_listener_settings()
    assert env.sets == [
        ("ipv4", "default"),
        ("ipv6", "default"),
        ("ipv4address", "default"),
        ("ipv6address", "default"),
        ("listenport", "default"),
    ]


def test_create_listeners_ipv4_only(monkeypatch: pytest.MonkeyPatch) -> None:
    env = Env(monkeypatch)
    env.obj.create_listeners()

    assert [c["host"] for c in env.server_calls] == ["127.0.0.1"]
    call = env.server_calls[0]
    assert call["port"] == 9999
    assert call["shell"] is net_client.client_telnet_handler
    assert call["force_binary"] is True
    assert call["compression"] is True
    assert call["encoding_errors"] == "replace"
    assert [name for _, name in env.added] == [
        "Proxy Telnet Listener IPv4",
        "Check Listeners Available",
    ]
    assert env.obj.ipv4_task is not None
    assert env.obj.ipv6_task is None
    assert env.obj.check_listener_task is not None


def test_create_listeners_both_families(monkeypatch: pytest.MonkeyPatch) -> None:
    env = Env(monkeypatch, ipv6=True)
    env.obj.create_listeners()
    assert [c["host"] for c in env.server_calls] == ["127.0.0.1", "::1"]
    assert env.obj.ipv6_task is not None
    assert [name for _, name in env.added][:2] == [
        "Proxy Telnet Listener IPv4",
        "Proxy Telnet Listener IPv6",
    ]


def test_create_listeners_enables_ipv4_when_nothing_is_enabled(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    env = Env(monkeypatch, ipv4=False, ipv6=False)
    with caplog.at_level(logging.ERROR, logger="mudproxy"):
        env.obj.create_listeners()
    assert ("ipv4", True) in env.sets
    assert [c["host"] for c in env.server_calls] == ["127.0.0.1"]
    assert any("No listeners enabled" in r.getMessage() for r in caplog.records)


async def test_both_listeners_up_logs_listening_on_both(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    env = Env(monkeypatch, ipv6=True)
    env.obj.ipv4_task = FakeTask()  # type: ignore[assignment]
    env.obj.ipv6_task = FakeTask()  # type: ignore[assignment]
    with caplog.at_level(logging.INFO, logger="mudproxy"):
        await asyncio.wait_for(env.obj.check_listeners_available(), 5)
    assert any(r.getMessage() == "Listening on IPv4 and IPv6 port 9999" for r in caplog.records)
    assert env.sets == []
    assert env.obj.listener_tries == 1


async def test_one_listener_up_logs_the_other_failure(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    env = Env(monkeypatch, ipv6=True)
    env.obj.ipv4_task = FakeTask()  # type: ignore[assignment]
    env.obj.ipv6_task = FakeTask(OSError("no ipv6"))  # type: ignore[assignment]
    with caplog.at_level(logging.INFO, logger="mudproxy"):
        await asyncio.wait_for(env.obj.check_listeners_available(), 5)
    messages = [r.getMessage() for r in caplog.records]
    assert "Listening on IPv4 port 9999" in messages
    assert any(m.startswith("IPv6 Listener did not start on ::1:9999") for m in messages)
    assert not any("resetting to defaults" in m for m in messages)
    assert env.sets == []


async def test_only_ipv6_up_reports_ipv6(monkeypatch: pytest.MonkeyPatch) -> None:
    env = Env(monkeypatch, ipv4=False, ipv6=True)
    env.obj.ipv6_task = FakeTask()  # type: ignore[assignment]
    await asyncio.wait_for(env.obj.check_listeners_available(), 5)
    assert env.obj.ipv4_start is False
    assert env.obj.ipv6_start is True


async def test_none_up_resets_settings_and_retries(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    env = Env(monkeypatch, ipv6=True)
    env.obj.ipv4_task = FakeTask(OSError("in use"))  # type: ignore[assignment]
    env.obj.ipv6_task = FakeTask(OSError("in use"))  # type: ignore[assignment]
    with caplog.at_level(logging.ERROR, logger="mudproxy"):
        await asyncio.wait_for(env.obj.check_listeners_available(), 5)

    messages = [r.getMessage() for r in caplog.records]
    assert any(m.startswith("IPv4 Listener did not start on 127.0.0.1:9999") for m in messages)
    assert any(m.startswith("IPv6 Listener did not start on ::1:9999") for m in messages)
    assert "No listeners available, resetting to defaults" in messages
    assert [key for key, value in env.sets if value == "default"] == [
        "ipv4",
        "ipv6",
        "ipv4address",
        "ipv6address",
        "listenport",
    ]
    assert env.obj.listener_tries == 2
    # listeners were created again, and the new check task is named for the retry
    assert len(env.server_calls) == 2
    assert env.added[-1][1] == "Check Listeners Available - Try 2"


async def test_gives_up_with_exit_after_retry_failed(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    env = Env(monkeypatch)
    env.obj.listener_tries = 3
    exits: list[int] = []

    def fake_exit(code: int) -> None:
        exits.append(code)
        raise SystemExit(code)

    monkeypatch.setattr(listeners_mod.sys, "exit", fake_exit)
    with caplog.at_level(logging.ERROR, logger="mudproxy"), pytest.raises(SystemExit):
        await asyncio.wait_for(env.obj.check_listeners_available(), 5)
    assert exits == [1]
    assert any("defaults did not work" in r.getMessage() for r in caplog.records)
    assert env.sets == []


async def test_full_retry_then_exit(monkeypatch: pytest.MonkeyPatch) -> None:
    """Each failed check resets and retries; the third check exits."""
    env = Env(monkeypatch)
    env.obj.ipv4_task = FakeTask(OSError("in use"))  # type: ignore[assignment]
    monkeypatch.setattr(
        listeners_mod.sys, "exit", lambda code: (_ for _ in ()).throw(SystemExit(code))
    )

    await env.obj.check_listeners_available()
    env.obj.ipv4_task = FakeTask(OSError("still in use"))  # type: ignore[assignment]
    await env.obj.check_listeners_available()
    assert env.obj.listener_tries == 3
    with pytest.raises(SystemExit):
        await env.obj.check_listeners_available()
