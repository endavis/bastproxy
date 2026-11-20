"""Tests for bastproxy.libs.commandsplit (#639)."""

import re

import pytest

from bastproxy.libs.commandsplit import build_command_split_regex


def test_pipe_splits_commands() -> None:
    assert re.split(build_command_split_regex("|"), "look|score") == ["look", "score"]


def test_doubled_separator_does_not_split() -> None:
    assert re.split(build_command_split_regex("|"), "say a||b") == ["say a||b"]


@pytest.mark.parametrize("sep", [";", "~", "^", "]", "\\", ".", "*", "$", "-", "[", "+", "?"])
def test_separator_splits_literally(sep: str) -> None:
    regex = build_command_split_regex(sep)
    assert re.split(regex, f"look{sep}score") == ["look", "score"]
    assert re.split(regex, f"say a{sep}{sep}b") == [f"say a{sep}{sep}b"]
    assert re.split(regex, "lookXscore") == ["lookXscore"]
