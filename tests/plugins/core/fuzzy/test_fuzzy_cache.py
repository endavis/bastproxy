"""Tests for the fuzzy plugin's matching APIs and their module-level caches (#6)."""

import gc
import weakref
from typing import Any

from bastproxy.plugins.core.fuzzy.plugin import _fuzzy
from bastproxy.plugins.core.fuzzy.plugin._fuzzy import FuzzyPlugin

CHOICES = ("apple", "apricot", "banana", "bandana", "cherry")


class _Stub(FuzzyPlugin):
    """A FuzzyPlugin that skips __init__."""

    def __init__(self) -> None:
        self.plugin_id = "plugins.core.fuzzy"


def _stub() -> Any:
    return _Stub()


def test_best_exact() -> None:
    assert _stub()._api_string_match_best("banana", CHOICES) == "banana"


def test_best_startswith() -> None:
    assert _stub()._api_string_match_best("che", CHOICES) == "cherry"


def test_best_score() -> None:
    assert _stub()._api_string_match_best("cheryy", CHOICES) == "cherry"


def test_best_no_match() -> None:
    assert _stub()._api_string_match_best("zzzzzz", CHOICES) == ""


def test_top_exact_first() -> None:
    result = _stub()._api_string_match_top("banana", CHOICES)
    assert isinstance(result, list)
    assert result[0] == "banana"


def test_top_score() -> None:
    assert _stub()._api_string_match_top("cheryy", CHOICES, score_cutoff=70) == ["cherry"]


def test_top_no_match() -> None:
    assert _stub()._api_string_match_top("zzzzzz", CHOICES) == []


def test_top_startswith_prefix_is_not_special() -> None:
    result = _stub()._api_string_match_top("ap", CHOICES, score_cutoff=0, items=2)
    assert len(result) == 2


def test_mutating_top_result_does_not_change_next_call() -> None:
    stub = _stub()
    first = stub._api_string_match_top("banana", CHOICES)
    expected = list(first)
    first.append("junk")
    first.clear()
    assert stub._api_string_match_top("banana", CHOICES) == expected


def test_instance_not_held_by_cache() -> None:
    stub = _stub()
    ref = weakref.ref(stub)
    stub._api_string_match_best("banana", CHOICES)
    stub._api_string_match_top("banana", CHOICES)
    del stub
    gc.collect()
    assert ref() is None


def test_repeated_call_is_cache_hit() -> None:
    stub = _stub()
    stub._api_string_match_best("cache-hit-probe", CHOICES)
    hits = _fuzzy._match_best.cache_info().hits
    stub._api_string_match_best("cache-hit-probe", CHOICES)
    assert _fuzzy._match_best.cache_info().hits == hits + 1


def test_top_repeated_call_is_cache_hit() -> None:
    stub = _stub()
    stub._api_string_match_top("cache-hit-probe", CHOICES)
    hits = _fuzzy._match_top.cache_info().hits
    stub._api_string_match_top("cache-hit-probe", CHOICES)
    assert _fuzzy._match_top.cache_info().hits == hits + 1
