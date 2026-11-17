# Project: bastproxy
# Filename: plugins/core/colors/libs/_sgr.py
#
# File Description: SGR parameter semantics for the ansi to colour-code conversion
#
# By: Bast
"""Follow ANSI SGR state across a line and write the ``@`` codes that reproduce it.

The SGR syntax itself lives in ``_tokenizer`` (:func:`split_sgr`). This module only decides what
the parameters mean: it applies them to a small ``(fg, bold, bg)`` state, then writes the minimal
``@`` codes between the last state written and the current one, and only before visible text.
"""

# Standard Library
import functools

# 3rd Party
# Project
from bastproxy.libs.logger import get_logger
from bastproxy.plugins.core.colors.libs._tokenizer import split_sgr

CANRELOAD = False

logger = get_logger(__name__)

# fg is None (default), ("b", n) basic 0-7, ("B", n) bright 0-7 or ("x", n) xterm 0-255
type Foreground = tuple[str, int] | None
# (fg, bold, bg); bg is None (default) or an xterm number 0-255
type SgrState = tuple[Foreground, bool, int | None]

DEFAULT_STATE: SgrState = (None, False, None)

_LOWER = "krgybmcw"
_UPPER = "DRGYBMCW"
_CUBE = (0, 95, 135, 175, 215, 255)
_MAX_COLOR = 255


def _nearest_level(value: int) -> int:
    """Return the index of the 6x6x6 cube level nearest to ``value``."""
    return min(range(len(_CUBE)), key=lambda i: abs(_CUBE[i] - value))


@functools.lru_cache(maxsize=256)
def rgb_to_xterm(red: int, green: int, blue: int) -> int:
    """Return the nearest xterm colour in 16-255 (0-15 are excluded, terminals redefine them)."""
    indexes = (_nearest_level(red), _nearest_level(green), _nearest_level(blue))
    cube = tuple(_CUBE[i] for i in indexes)
    cube_distance = sum((a - b) ** 2 for a, b in zip((red, green, blue), cube, strict=True))
    grey_index = max(0, min(23, round(((red + green + blue) / 3 - 8) / 10)))
    grey = 8 + 10 * grey_index
    grey_distance = sum((a - grey) ** 2 for a in (red, green, blue))
    if cube_distance <= grey_distance:
        return 16 + 36 * indexes[0] + 6 * indexes[1] + indexes[2]
    return 232 + grey_index


@functools.lru_cache(maxsize=1024)
def apply_sgr(state: SgrState, params: str) -> SgrState:
    """Apply one SGR parameter string to ``state`` and return the new state.

    Parameters with no ``@`` code (underline, reverse, ...) are ignored. A malformed 38/48
    stops the parse of this sequence and keeps what came before.
    """
    fg, bold, bg = state
    values = [int(part) if part else 0 for part in params.split(";")]
    index = 0
    while index < len(values):
        number = values[index]
        index += 1
        if number == 0:
            fg, bold, bg = DEFAULT_STATE
        elif number == 1:
            bold = True
        elif number == 22:
            bold = False
        elif 30 <= number <= 37:
            fg = ("b", number - 30)
        elif 90 <= number <= 97:
            fg = ("B", number - 90)
        elif number == 39:
            fg = None
        elif 40 <= number <= 47:
            bg = number - 40
        elif 100 <= number <= 107:
            bg = number - 100 + 8
        elif number == 49:
            bg = None
        elif number in (38, 48):
            color: int | None = None
            rest = values[index:]
            if len(rest) >= 2 and rest[0] == 5 and rest[1] <= _MAX_COLOR:
                color = rest[1]
                index += 2
            elif len(rest) >= 4 and rest[0] == 2 and max(rest[1:4]) <= _MAX_COLOR:
                color = rgb_to_xterm(rest[1], rest[2], rest[3])
                index += 4
            if color is None:
                logger.debug("ignoring malformed ansi colour sequence %r", params)
                break
            if number == 38:
                fg = ("x", color)
            else:
                bg = color
    return (fg, bold, bg)


def fg_code(state: SgrState) -> str:
    """Return the colour letter (or ``x<n>``) for the foreground of ``state``, or ``""``."""
    fg, bold, _ = state
    if fg is None:
        return "W" if bold else ""
    kind, value = fg
    if kind == "x":
        return f"x{value}"
    if kind == "B" or bold:
        return _UPPER[value]
    return _LOWER[value]


@functools.lru_cache(maxsize=1024)
def diff_codes(emitted: SgrState, target: SgrState) -> str:
    """Return the ``@`` codes that take the written state ``emitted`` to ``target``."""
    if emitted == target:
        return ""
    out: list[str] = []
    current_fg = fg_code(emitted)
    current_bg = emitted[2]
    if (
        (target[0] is None and emitted[0] is not None)
        or (target[2] is None and current_bg is not None)
        or (target[0] is None and emitted[1] and not target[1])
    ):
        out.append("@w")
        current_fg = ""
        current_bg = None
    wanted_fg = fg_code(target)
    if wanted_fg != current_fg:
        out.append(f"@{wanted_fg}")
    if target[2] != current_bg:
        out.append(f"@z{target[2]}")
    return "".join(out)


def sgr_to_colorcode(text: str) -> str:
    """Convert the SGR sequences in ``text`` to ``@`` codes, writing codes only before text."""
    parts = split_sgr(text)
    if len(parts) == 1:
        return text
    out = [parts[0]] if parts[0] else []
    emitted = target = DEFAULT_STATE
    for index in range(1, len(parts), 2):
        target = apply_sgr(target, parts[index])
        segment = parts[index + 1]
        if segment:
            if target != emitted:
                out.append(diff_codes(emitted, target))
                emitted = target
            out.append(segment)
    return "".join(out)
