"""Regression tests for #277: an async callback must be rejected at registration."""

# Standard Library
import logging

# 3rd Party
import pytest

# Project
from bastproxy.plugins.core.events.plugin._event import Event

OWNER_ID = "zz277.owner"
EVENT_NAME = "ev_test277"


class _Owner:
    """A plugin-like object with sync and async callbacks."""

    async def async_cb(self) -> None:
        return None

    def sync_cb(self) -> None:
        return None


async def _async_plain() -> None:
    return None


def _sync_plain() -> None:
    return None


def _event() -> Event:
    return Event(EVENT_NAME, created_by="test277")


def test_async_bound_method_rejected(caplog: pytest.LogCaptureFixture) -> None:
    event = _event()
    with caplog.at_level(logging.ERROR):
        assert event.register(_Owner().async_cb, OWNER_ID, 50) is False
    assert event.priority_dictionary == {}
    assert event.count() == 0
    assert "async_cb" in caplog.text
    assert EVENT_NAME in caplog.text


def test_async_plain_function_rejected(caplog: pytest.LogCaptureFixture) -> None:
    event = _event()
    with caplog.at_level(logging.ERROR):
        assert event.register(_async_plain, OWNER_ID, 30) is False
    assert event.priority_dictionary == {}
    assert "_async_plain" in caplog.text
    assert EVENT_NAME in caplog.text


def test_sync_callbacks_still_register() -> None:
    event = _event()
    assert event.register(_Owner().sync_cb, OWNER_ID, 50) is True
    assert event.register(_sync_plain, OWNER_ID, 60) is True
    assert event.count() == 2
