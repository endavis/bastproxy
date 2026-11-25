"""Tests for the case-insensitive command prefix helpers (#782)."""

import pytest

from bastproxy.libs.commandprefix import normalize_command_prefix, starts_with_command_prefix


@pytest.mark.parametrize("text", ["#bp.x", "#BP.x", "#Bp", "  #BP.core"])
def test_starts_with_prefix_in_any_case(text: str) -> None:
    assert starts_with_command_prefix(text, "#bp") is True


@pytest.mark.parametrize("text", ["look", "#b", "x#bp", ""])
def test_does_not_start_with_prefix(text: str) -> None:
    assert starts_with_command_prefix(text, "#bp") is False


def test_empty_prefix_never_matches() -> None:
    assert starts_with_command_prefix("#bp.x", "") is False
    assert normalize_command_prefix("#bp.x", "") == "#bp.x"


def test_normalize_rewrites_prefix_case() -> None:
    assert normalize_command_prefix("#BP.core.proxy.info -h", "#bp") == "#bp.core.proxy.info -h"


def test_normalize_leaves_other_text_unchanged() -> None:
    assert normalize_command_prefix("say #BP", "#bp") == "say #BP"
    assert normalize_command_prefix("  look", "#bp") == "  look"
