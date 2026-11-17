# Project: bastproxy
# Filename: libs/textwidth.py
#
# File Description: display width of visible text, in terminal columns
#
# By: Bast
"""Display width of visible text, measured in terminal columns.

``len()`` counts code points, which is wrong for wide characters (CJK and emoji take two
columns), combining marks and joiners (zero columns). This module measures columns with
``wcwidth`` so every width path in the framework agrees.

The text given here must already be free of colour codes. Each caller strips them the way it
already does, through the colors API or the tokenizer, and passes the visible text.

Contract:
    - The width is never negative.
    - Control characters and terminal escape sequences count as zero columns.
    - :func:`text_units` splits text into units (graphemes) whose widths sum to
      :func:`display_width`, so a caller can wrap without cutting a character apart.
"""

# Standard Library
# 3rd Party
import wcwidth

# Project


def display_width(text: str) -> int:
    """Return the number of terminal columns the visible ``text`` takes.

    Args:
        text: Visible text with the colour codes already stripped.

    Returns:
        The width in columns, never negative. Control characters count as zero.

    """
    if text.isascii() and text.isprintable():
        return len(text)
    return wcwidth.width(text, control_codes="ignore")


def text_units(text: str) -> list[tuple[str, int]]:
    """Split visible ``text`` into ``(unit, width)`` pairs.

    A unit is one grapheme (a base character with its combining marks, a ZWJ sequence, a
    flag) or one terminal escape sequence, which has width zero. The widths sum to
    :func:`display_width` of the same text.

    Args:
        text: Visible text with the colour codes already stripped.

    Returns:
        The units in order; joining them gives back ``text``.

    """
    if text.isascii() and text.isprintable():
        return [(char, 1) for char in text]
    units: list[tuple[str, int]] = []
    for segment, is_sequence in wcwidth.iter_sequences(text):
        if is_sequence:
            units.append((segment, 0))
            continue
        units.extend(
            (grapheme, wcwidth.width(grapheme, control_codes="ignore"))
            for grapheme in wcwidth.iter_graphemes(segment)
        )
    return units
