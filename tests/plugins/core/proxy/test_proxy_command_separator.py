"""Tests for the cmdseperator setting of the proxy plugin (#639)."""

import re
from unittest.mock import MagicMock

import pytest

from bastproxy.libs.api import API
from bastproxy.plugins.core.proxy.plugin._proxy import ProxyPlugin


def test_callback_builds_a_literal_regex(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(API, "command_split_regex", None)
    stub = MagicMock()
    stub.api.__class__ = API
    stub.api.side_effect = lambda _name: lambda *_a, **_k: {"newvalue": "."}

    ProxyPlugin._eventcb_command_seperator_change(stub)

    assert API.command_split_regex is not None
    assert re.split(API.command_split_regex, "look.score") == ["look", "score"]
    assert re.split(API.command_split_regex, "lookXscore") == ["lookXscore"]


def test_callback_publishes_the_separator(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(API, "command_separator", "|")
    stub = MagicMock()
    stub.api.__class__ = API
    stub.api.side_effect = lambda _name: lambda *_a, **_k: {"newvalue": ";"}

    ProxyPlugin._eventcb_command_seperator_change(stub)

    assert API.command_separator == ";"
