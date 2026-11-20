"""Tests for temporary bans surviving a clients plugin reload (#640)."""

import datetime
from typing import Any
from unittest.mock import MagicMock, patch

from bastproxy.plugins.core.clients.plugin import _clients
from bastproxy.plugins.core.clients.plugin._clients import BanRecord, ClientPlugin

PID = "plugins.core.clients"
NOW = datetime.datetime(2026, 1, 1, 12, 0, 0, tzinfo=datetime.UTC)


class FakeTimers:
    """Stand-in for the timers plugin API."""

    def __init__(self) -> None:
        self.timers: dict[str, float] = {}
        self.api = MagicMock(side_effect=self._api)
        self.api.time_format = "%a %b %d %Y %H:%M:%S %Z"

    def _api(self, name: str) -> Any:
        if name == "plugins.core.timers:timer.add":

            def add(timer: str, _func: Any, seconds: float, **_kw: Any) -> None:
                self.timers[timer] = seconds

            return add
        if name == "plugins.core.timers:timer.next.fire.get":
            return lambda timer: (
                NOW + datetime.timedelta(seconds=self.timers[timer])
                if timer in self.timers
                else None
            )
        return MagicMock()


def _record(fake: FakeTimers, how_long: int = 20) -> BanRecord:
    with patch.object(_clients, "API", return_value=fake.api):
        return BanRecord(PID, "192.0.2.9", how_long=how_long)


def _reload(fake: FakeTimers, record: BanRecord) -> BanRecord:
    fake.timers.clear()  # the timers plugin removed the old plugin's timers
    with patch.object(_clients, "API", return_value=fake.api):
        return record.copy(BanRecord)


def _at(offset: float) -> Any:
    return patch.object(
        _clients.datetime,
        "datetime",
        MagicMock(now=lambda _tz=None: NOW + datetime.timedelta(seconds=offset)),
    )


def test_copy_recreates_timer_for_remaining_time() -> None:
    fake = FakeTimers()
    with _at(0):
        record = _record(fake, 20)
    with _at(8):
        new = _reload(fake, record)
    assert fake.timers[new.timer_name] == 12
    assert new.expires_at == record.expires_at


def test_copy_timer_minimum_one_second() -> None:
    fake = FakeTimers()
    with _at(0):
        record = _record(fake, 20)
    with _at(19.9):
        new = _reload(fake, record)
    assert fake.timers[new.timer_name] == 1


def test_expired_ban_is_dropped_on_initialize() -> None:
    fake = FakeTimers()
    with _at(0):
        record = _record(fake, 20)
    stub = MagicMock()
    stub.plugin_id = PID
    stub.banned = {"192.0.2.9": record}
    with _at(30), patch.object(_clients, "API", return_value=fake.api):
        fake.timers.clear()
        ClientPlugin._phook_initialize(stub)
    assert stub.banned == {}
    assert fake.timers == {}


def test_initialize_keeps_unexpired_ban_and_shows_expiry() -> None:
    fake = FakeTimers()
    with _at(0):
        record = _record(fake, 20)
    stub = MagicMock()
    stub.plugin_id = PID
    stub.banned = {"192.0.2.9": record}
    with _at(5), patch.object(_clients, "API", return_value=fake.api):
        fake.timers.clear()
        ClientPlugin._phook_initialize(stub)
        new = stub.banned["192.0.2.9"]
        assert new is not record
        assert new.expires != "Permanent"


def test_permanent_ban_record_unaffected() -> None:
    fake = FakeTimers()
    with _at(0):
        record = _record(fake, 0)
    assert record.expires_at is None
    with _at(1000):
        new = _reload(fake, record)
    assert fake.timers == {}
    assert not new.has_expired
    assert new.expires == "Permanent"
