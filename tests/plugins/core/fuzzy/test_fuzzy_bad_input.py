"""Tests for the fuzzy APIs with an empty list or an unknown scorer (#673)."""

import inspect
import logging
from typing import Any

import pytest

from bastproxy.plugins.core.fuzzy.plugin import _fuzzy
from bastproxy.plugins.core.fuzzy.plugin._fuzzy import FuzzyPlugin

CHOICES = ("apple", "apricot", "banana", "bandana", "cherry")


class _Stub(FuzzyPlugin):
    """A FuzzyPlugin that skips __init__."""

    def __init__(self) -> None:
        self.plugin_id = "plugins.core.fuzzy"


def _stub() -> Any:
    return _Stub()


def _errors(caplog: pytest.LogCaptureFixture) -> list[logging.LogRecord]:
    return [r for r in caplog.records if r.levelno == logging.ERROR]


def test_best_empty_list_is_empty_string() -> None:
    assert _stub()._api_string_match_best("apple", ()) == ""


def test_match_best_empty_list_called_directly() -> None:
    assert _fuzzy._match_best("apple", (), 80, "ratio") == ""


def test_top_empty_list_is_empty() -> None:
    assert _stub()._api_string_match_top("apple", ()) == []
    assert _fuzzy._match_top("apple", (), 5, 80, "ratio") == ()


@pytest.mark.parametrize("scorer", ["nosuch", "os"])
def test_unknown_scorer_logs_and_finds_nothing(
    scorer: str, caplog: pytest.LogCaptureFixture
) -> None:
    with caplog.at_level(logging.ERROR):
        assert _stub()._api_string_match_best("apple", CHOICES, scorer=scorer) == ""
        assert _stub()._api_string_match_top("apple", CHOICES, scorer=scorer) == []
    assert len(_errors(caplog)) == 2
    assert scorer in _errors(caplog)[0].getMessage()


def test_refused_calls_log_each_time_and_leave_cache_alone(
    caplog: pytest.LogCaptureFixture,
) -> None:
    best = _fuzzy._match_best.cache_info().currsize
    top = _fuzzy._match_top.cache_info().currsize
    with caplog.at_level(logging.ERROR):
        _stub()._api_string_match_best("apple", CHOICES, scorer="nosuch")
        _stub()._api_string_match_best("apple", CHOICES, scorer="nosuch")
    assert len(_errors(caplog)) == 2
    assert _fuzzy._match_best.cache_info().currsize == best
    assert _fuzzy._match_top.cache_info().currsize == top


@pytest.mark.parametrize("scorer", sorted(_fuzzy._SCORERS))
def test_every_listed_scorer_works(scorer: str) -> None:
    assert _stub()._api_string_match_best("banana", CHOICES, scorer=scorer) == "banana"
    assert "banana" in _stub()._api_string_match_top("banana", CHOICES, scorer=scorer)


def test_texts() -> None:
    assert "command parsing" not in (FuzzyPlugin.__doc__ or "")
    assert "None" not in (FuzzyPlugin._api_string_match_best.__doc__ or "")
    assert "fuzzywuzzy" not in inspect.getsource(_fuzzy)
