"""Regression tests for #276: raise_event with data that is not a dict."""

# Standard Library
import logging
from typing import Any

# 3rd Party
import pytest

# Project
from bastproxy.plugins.core.events.plugin import _event
from bastproxy.plugins.core.events.plugin._event import Event


def test_non_dict_data_logs_error_and_returns_none(monkeypatch: pytest.MonkeyPatch) -> None:
    """Rejected data logs the event and the actor, then returns None."""
    calls: list[tuple[Any, ...]] = []

    def fake_log_to(sources: Any, level: int, msg: str, *args: object, **_kw: Any) -> None:
        calls.append((level, msg, args))

    monkeypatch.setattr(_event, "log_to", fake_log_to)
    event = Event("ev_probe276", created_by="probe276")

    assert event.raise_event("not a dict", "actor276") is None  # type: ignore[arg-type]
    assert calls[0][0] == logging.ERROR
    assert calls[0][2] == ("ev_probe276", "actor276")
