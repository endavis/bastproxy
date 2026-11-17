"""The colour-code tokenizer is the one definition of the syntax (#534)."""

import re
from pathlib import Path

import pytest

import bastproxy
from bastproxy.plugins.core.colors.libs import _tokenizer
from bastproxy.plugins.core.colors.libs._tokenizer import (
    BASIC_COLORS,
    Token,
    TokenKind,
    strip_ansi,
    strip_colorcodes,
    tokenize,
)

ROUND_TRIP_INPUTS = [
    "",
    "plain",
    "@@",
    "@-",
    "@@-",
    "@Rfoo@w",
    "@x075a@z165b",
    "@x0751",
    "@x256",
    "@xab",
    "@x",
    "@1@a@\n",
    "trailing@",
    "\x1b[m\x1b[0m\x1b[1;37;44m\x1b[38;5;196m\x1b[38;2;1;2;3m\x1b[;31m",
    "\x1b",
    "\x1b[2J",
    "mix @R\x1b[31m@@ @x300 end@",
]


def kinds(text: str) -> list[tuple[TokenKind, str]]:
    return [(token.kind, token.raw) for token in tokenize(text)]


@pytest.mark.parametrize("text", ROUND_TRIP_INPUTS)
def test_raw_text_joins_back_to_the_input(text: str) -> None:
    assert "".join(token.raw for token in tokenize(text)) == text


def test_escapes_show_one_character() -> None:
    assert [(t.kind, t.visible) for t in tokenize("@@@-")] == [
        (TokenKind.ESCAPE, "@"),
        (TokenKind.ESCAPE, "~"),
    ]


@pytest.mark.parametrize("letter", list("krgybmcwDRGYBMCW"))
def test_every_basic_letter_is_a_color(letter: str) -> None:
    assert letter in BASIC_COLORS
    assert tokenize(f"@{letter}") == [Token(TokenKind.COLOR, f"@{letter}", "", letter)]


def test_basic_letters_do_not_include_the_reset() -> None:
    assert "x" not in BASIC_COLORS
    assert len(BASIC_COLORS) == 16


@pytest.mark.parametrize(
    ("text", "kind", "value"),
    [
        ("@x0", TokenKind.XTERM_FG, "0"),
        ("@x255", TokenKind.XTERM_FG, "255"),
        ("@x075", TokenKind.XTERM_FG, "075"),
        ("@z075", TokenKind.XTERM_BG, "075"),
        ("@z0", TokenKind.XTERM_BG, "0"),
    ],
)
def test_xterm_codes_keep_digits_as_written(text: str, kind: TokenKind, value: str) -> None:
    assert tokenize(text) == [Token(kind, text, "", value)]


@pytest.mark.parametrize("text", ["@x256", "@x999", "@z300"])
def test_out_of_range_xterm_is_invalid(text: str) -> None:
    assert kinds(text) == [(TokenKind.INVALID, text)]


def test_xterm_takes_at_most_three_digits() -> None:
    assert kinds("@x0751") == [(TokenKind.XTERM_FG, "@x075"), (TokenKind.TEXT, "1")]


def test_xterm_without_digits_keeps_the_next_characters() -> None:
    assert kinds("@xab") == [(TokenKind.INVALID, "@x"), (TokenKind.TEXT, "ab")]


@pytest.mark.parametrize("text", ["@1", "@a", "@\n"])
def test_unknown_at_sequences_are_invalid(text: str) -> None:
    assert kinds(text) == [(TokenKind.INVALID, text)]


def test_trailing_at_is_text() -> None:
    assert kinds("abc@") == [(TokenKind.TEXT, "abc"), (TokenKind.TEXT, "@")]


def test_escape_binds_before_a_following_tilde_escape() -> None:
    assert kinds("@@-") == [(TokenKind.ESCAPE, "@@"), (TokenKind.TEXT, "-")]


@pytest.mark.parametrize(
    ("text", "params"),
    [
        ("\x1b[m", ""),
        ("\x1b[0m", "0"),
        ("\x1b[1;37;44m", "1;37;44"),
        ("\x1b[38;5;196m", "38;5;196"),
        ("\x1b[38;2;1;2;3m", "38;2;1;2;3"),
        ("\x1b[;31m", ";31"),
    ],
)
def test_sgr_forms_are_one_token(text: str, params: str) -> None:
    assert tokenize(text) == [Token(TokenKind.SGR, text, "", params)]


def test_lone_escape_and_other_sequences_are_text() -> None:
    assert kinds("\x1b") == [(TokenKind.TEXT, "\x1b")]
    assert kinds("\x1b[2J") == [(TokenKind.TEXT, "\x1b"), (TokenKind.TEXT, "[2J")]


def test_strip_helpers() -> None:
    assert strip_colorcodes("@Rfoo@@\x1b[1mbar@w") == "foo@bar"
    assert strip_ansi("\x1b[1mfoo@R\x1b[2J") == "foo@R\x1b[2J"
    assert strip_colorcodes("plain") == "plain"
    assert strip_ansi("plain") == "plain"


def test_only_the_tokenizer_defines_the_colour_syntax() -> None:
    """No other module compiles a pattern for ``@`` codes or SGR sequences."""
    assert _tokenizer.CANRELOAD is False
    root = Path(bastproxy.__file__).parent
    pattern = re.compile(r"""(@\[|\\x1b\\\[|\[0-9;\]\*m)""")
    offenders = [
        str(path.relative_to(root))
        for path in root.rglob("*.py")
        if path.name not in ("_tokenizer.py", "mxp.py") and pattern.search(path.read_text())
    ]
    assert offenders == []
