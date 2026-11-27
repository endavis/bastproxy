# Project: bastproxy
# Filename: plugins/core/colors/libs/_spans.py
#
# File Description: turn the tokens of one line into styled spans
#
# By: Bast
"""Turn the tokens of one line into spans: runs of visible text with the colour in force.

The syntax lives in ``_tokenizer``; this module only applies the meaning of each token to a
``(fg, bg, bold)`` state. It never reads the text itself. A span ends at every colour code, even
when the style does not change, and empty spans are never produced.
"""

# Standard Library
from dataclasses import asdict, dataclass

# 3rd Party
# Project
from bastproxy.plugins.core.colors.libs._colors import LETTER_INDEX
from bastproxy.plugins.core.colors.libs._tokenizer import Token, TokenKind

CANRELOAD = False

# @w is the general reset: it clears the background as well as setting white
RESET_CODE = "w"
_BOLD_LETTERS = "DRGYBMCW"


@dataclass(frozen=True, slots=True)
class Span:
    """A run of visible text with its style; colours are 256-colour indexes or ``None``."""

    text: str
    fg: int | None = None
    bg: int | None = None
    bold: bool = False

    def as_dict(self) -> dict[str, str | int | bool | None]:
        """Return the span as a plain dict, the shape that crosses the API."""
        return dict(asdict(self))


def line_spans(tokens: list[Token]) -> list[Span]:
    """Build the spans for the tokens of one line; the style starts at its default."""
    fg: int | None = None
    bg: int | None = None
    bold = False
    out: list[Span] = []
    buffer: list[str] = []
    started = (fg, bg, bold)

    def flush() -> None:
        if buffer:
            out.append(Span("".join(buffer), started[0], started[1], started[2]))
            buffer.clear()

    for token in tokens:
        kind = token.kind
        if kind in (TokenKind.TEXT, TokenKind.ESCAPE):
            buffer.append(token.visible)
        elif kind in (TokenKind.COLOR, TokenKind.XTERM_FG, TokenKind.XTERM_BG):
            flush()
            if kind is TokenKind.COLOR:
                if token.value == RESET_CODE:
                    fg, bg, bold = None, None, False
                else:
                    fg = LETTER_INDEX[token.value]
                    bold = token.value in _BOLD_LETTERS
            elif kind is TokenKind.XTERM_FG:
                fg = int(token.value)
                bold = False
            else:
                bg = int(token.value)
            started = (fg, bg, bold)
    flush()
    return out
