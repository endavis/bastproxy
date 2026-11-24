"""Tests for the gc freeze helper (#758)."""

import gc
import logging
import weakref
from collections.abc import Iterator
from typing import Any
from unittest.mock import MagicMock

import pytest

from bastproxy.libs import gcfreeze


@pytest.fixture
def fake_gc(monkeypatch: pytest.MonkeyPatch) -> MagicMock:
    fake = MagicMock()
    fake.get_freeze_count.return_value = 123
    fake.collect.return_value = 7
    monkeypatch.setattr(gcfreeze, "gc", fake)
    monkeypatch.setattr(gcfreeze, "_frozen", False)
    return fake


def _names(fake: MagicMock, wanted: tuple[str, ...]) -> list[str]:
    return [c[0] for c in fake.mock_calls if c[0] in wanted]


def test_freeze_collects_then_freezes(fake_gc: MagicMock, caplog: pytest.LogCaptureFixture) -> None:
    with caplog.at_level(logging.INFO):
        count = gcfreeze.freeze_long_lived_objects("startup")
    assert count == 123
    assert _names(fake_gc, ("collect", "freeze")) == ["collect", "freeze"]
    assert gcfreeze.is_frozen()
    text = "\n".join(r.getMessage() for r in caplog.records)
    assert "startup" in text
    assert "frozen=123" in text


def test_refreeze_before_freeze_is_noop(fake_gc: MagicMock) -> None:
    assert gcfreeze.refreeze("x") is None
    assert fake_gc.mock_calls == []


def test_refreeze_order_and_log(fake_gc: MagicMock, caplog: pytest.LogCaptureFixture) -> None:
    gcfreeze.freeze_long_lived_objects("startup")
    fake_gc.reset_mock()
    fake_gc.get_freeze_count.return_value = 99
    with caplog.at_level(logging.INFO):
        assert gcfreeze.refreeze("after reload a") == 99
    assert _names(fake_gc, ("unfreeze", "collect", "freeze")) == ["unfreeze", "collect", "freeze"]
    assert any("after reload a" in r.getMessage() for r in caplog.records)


class _Cyclic:
    def __init__(self) -> None:
        self.me: Any = self


@pytest.fixture
def real_gc(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    monkeypatch.setattr(gcfreeze, "_frozen", False)
    try:
        yield
    finally:
        gc.unfreeze()
    assert gc.get_freeze_count() == 0


def test_refreeze_reclaims_frozen_cycle(real_gc: None) -> None:
    obj = _Cyclic()
    ref = weakref.ref(obj)
    gcfreeze.freeze_long_lived_objects("test")
    del obj
    gc.collect()
    assert ref() is not None  # the frozen cycle survives a plain collection
    gcfreeze.refreeze("test")
    assert ref() is None
