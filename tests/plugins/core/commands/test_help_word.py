"""Tests for #791: a lone ``help`` argument acts as ``-h`` when no positional could hold it."""

# 3rd Party
import pytest

# Project
from bastproxy.libs import argp

from .test_parse_args_strict import _command_with, _parser, _patch_command_module

__all__ = ["_patch_command_module"]


def test_lone_help_shows_help_without_positional() -> None:
    ran: list[bool] = []
    result = _command_with(_parser(), ran).run("help")
    assert result.success is True
    assert result.reason == "help"
    assert any("--flag" in line for line in result.message)
    assert ran == []


def test_dash_h_still_works() -> None:
    parsed = _command_with(_parser(), []).parse_args("-h")
    assert parsed.success is True


def test_optional_positional_keeps_the_word() -> None:
    parser = _parser()
    parser.add_argument("match", nargs="?", default="")
    parsed = _command_with(parser, []).parse_args("help")
    assert parsed.success is True
    assert parsed.args.match == "help"  # type: ignore[union-attr]


def test_required_positional_takes_the_word() -> None:
    parser = argp.ArgumentParser(add_help=False)
    parser.add_argument("-h", "--help", action="store_true")
    parser.add_argument("name")
    parsed = _command_with(parser, []).parse_args("help")
    assert parsed.success is True
    assert parsed.args.name == "help"  # type: ignore[union-attr]


@pytest.mark.parametrize("text", ["help me", "help help"])
def test_only_a_lone_word_counts(text: str) -> None:
    parsed = _command_with(_parser(), []).parse_args(text)
    assert parsed.success is False
    assert "unrecognized arguments" in parsed.message[0]
