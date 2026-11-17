# Project: bastproxy
# Filename: plugins/core/colors/libs/_tokenizer.py
#
# File Description: the single definition of the colour-code syntax
#
# By: Bast
"""The one tokenizer for the colour-code syntax.

This module is the only place that defines the ``@`` colour codes and the ANSI SGR
(``ESC [ ... m``) syntax. Every colors API (conversion, stripping, validation, html, width) is
built on :func:`tokenize`. Other plugins never import this module; they reach it through the
``plugins.core.colors:colorcode.tokenize`` API.

The scan is one left-to-right pass over a single compiled pattern, so the result does not depend
on the order in which separate regular expressions would have been applied. The raw text of the
tokens always joins back to the input.
"""

# Standard Library
import re
from dataclasses import dataclass
from enum import Enum

# 3rd Party
# Project
from bastproxy.plugins.core.colors.libs._colors import CONVERTCOLORS

CANRELOAD = False

XTERM_MAX = 255

# the letters that are valid ``@`` colour codes (``x`` in CONVERTCOLORS is a reset, not a letter)
BASIC_COLORS: str = "".join(key for key in CONVERTCOLORS if key != "x")


class TokenKind(Enum):
    """The kinds of token found in a string."""

    TEXT = "text"
    ESCAPE = "escape"  # @@ (visible @) and @- (visible ~)
    COLOR = "color"  # @r, @R, ...
    XTERM_FG = "xterm_fg"  # @x075
    XTERM_BG = "xterm_bg"  # @z075
    SGR = "sgr"  # an ANSI colour escape sequence
    INVALID = "invalid"  # an @ sequence that is not a colour code; it is dropped


@dataclass(frozen=True, slots=True)
class Token:
    """One piece of a string.

    ``raw`` is the text as written. ``visible`` is what the token shows: the text itself for
    ``TEXT``, the single character for ``ESCAPE`` and empty for every other kind. ``value`` is
    the colour letter, the xterm number as written, or the SGR parameter string.
    """

    kind: TokenKind
    raw: str
    visible: str = ""
    value: str = ""


_TOKEN_RE = re.compile(
    r"\x1b\[(?P<sgr>[0-9;]*)m"
    r"|(?P<at>@@)"
    r"|(?P<tilde>@-)"
    r"|@(?P<xterm>[xz])(?P<digits>\d{1,3})"
    r"|(?P<badxterm>@[xz])"
    rf"|@(?P<color>[{BASIC_COLORS}])"
    r"|(?P<invalid>@.)"
    r"|(?P<lastat>@\Z)"
    r"|(?P<text>[^@\x1b]+|\x1b)",
    re.DOTALL,
)


def tokenize(text: str) -> list[Token]:
    """Split ``text`` into tokens; ``"".join(t.raw for t in tokenize(s)) == s``."""
    tokens: list[Token] = []
    for match in _TOKEN_RE.finditer(text):
        raw = match.group()
        kind = match.lastgroup
        if kind == "sgr":
            tokens.append(Token(TokenKind.SGR, raw, "", match.group("sgr")))
        elif kind == "at":
            tokens.append(Token(TokenKind.ESCAPE, raw, "@"))
        elif kind == "tilde":
            tokens.append(Token(TokenKind.ESCAPE, raw, "~"))
        elif kind == "digits":
            digits = match.group("digits")
            if int(digits) > XTERM_MAX:
                tokens.append(Token(TokenKind.INVALID, raw))
            else:
                is_fg = match.group("xterm") == "x"
                token_kind = TokenKind.XTERM_FG if is_fg else TokenKind.XTERM_BG
                tokens.append(Token(token_kind, raw, "", digits))
        elif kind == "color":
            tokens.append(Token(TokenKind.COLOR, raw, "", match.group("color")))
        elif kind in ("badxterm", "invalid"):
            tokens.append(Token(TokenKind.INVALID, raw))
        else:  # lastat and text
            tokens.append(Token(TokenKind.TEXT, raw, raw))
    return tokens


def strip_colorcodes(text: str) -> str:
    """Remove every colour code and SGR sequence from ``text``; escapes show their character."""
    if "@" not in text and "\x1b" not in text:
        return text
    return "".join(token.visible for token in tokenize(text))


def strip_ansi(text: str) -> str:
    """Remove every SGR sequence from ``text``; everything else is kept as written."""
    if "\x1b" not in text:
        return text
    return "".join(token.raw for token in tokenize(text) if token.kind is not TokenKind.SGR)
