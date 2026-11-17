"""Conversion, stripping and validation built on the tokenizer (#534).

The audit cases are in docs/claude/colors_findings.md (CO-1 to CO-4, CA-1 to CA-3).
"""

from unittest.mock import MagicMock

import pytest

from bastproxy.plugins.core.colors.libs._colors import CONVERTANSI
from bastproxy.plugins.core.colors.plugin._colors import ColorsPlugin


def to_ansi(text: str) -> str:
    result: str = ColorsPlugin._api_colorcode_to_ansicode(MagicMock(), text)
    return result


def cc_strip(text: str) -> str:
    result: str = ColorsPlugin._api_colorcode_strip(MagicMock(), text)
    return result


def ansi_strip(text: str) -> str:
    result: str = ColorsPlugin._api_ansicode_strip(MagicMock(), text)
    return result


def to_colorcode(text: str) -> str:
    result: str = ColorsPlugin._api_ansicode_to_colorcode(MagicMock(), text)
    return result


def is_valid(text: str) -> bool:
    result: bool = ColorsPlugin._api_colorcode_is_valid(MagicMock(), text)
    return result


# --- CO-1: an @ that is not a code no longer adds "@w" columns -------------------------------


def test_co1_escaped_at_keeps_its_width() -> None:
    assert cc_strip("mail@@host") == "mail@host"
    assert to_ansi("mail@@host") == "mail@host"


def test_co1_invalid_code_is_dropped_without_an_extra_reset() -> None:
    assert cc_strip("a@ab") == "ab"
    assert cc_strip("@R") == ""


# --- CO-2: k is a valid code -----------------------------------------------------------------


def test_co2_k_converts() -> None:
    assert to_ansi("@kblack@w") == "\x1b[0;30mblack\x1b[0m"


# --- CO-3: a lowercase colour re-applies the active background -------------------------------


def test_co3_lowercase_keeps_the_background() -> None:
    assert to_ansi("@z165@rtext") == "\x1b[48;5;165m\x1b[0;31;48;5;165mtext\x1b[0m"


def test_co3_uppercase_does_not_repeat_the_background() -> None:
    assert to_ansi("@z165@Rtext") == "\x1b[48;5;165m\x1b[1;31mtext\x1b[0m"


def test_co3_w_is_a_reset_and_clears_the_background() -> None:
    """@w stays the general reset: it does not re-apply the background (#534)."""
    assert to_ansi("@z165@wtext") == "\x1b[48;5;165m\x1b[0;37mtext\x1b[0m"


def test_co3_background_does_not_return_after_w() -> None:
    """The colors show swatch pattern: a lowercase code after @w gets no old background."""
    assert to_ansi("@z052    @w @rx") == "\x1b[48;5;052m    \x1b[0;37m \x1b[0;31mx\x1b[0m"


# --- CO-4: xterm values run 0 to 255 ----------------------------------------------------------


@pytest.mark.parametrize("code", ["@x255", "@z0", "@k", "@x0", "@r", "@W", "@z075"])
def test_co4_valid_codes(code: str) -> None:
    assert is_valid(code) is True


@pytest.mark.parametrize("code", ["@x256", "@x", "@x1234", "@q", "", "r", "@@", "@r@r", "@rx"])
def test_co4_invalid_codes(code: str) -> None:
    assert is_valid(code) is False


# --- CA-3: stripping drops every SGR sequence -------------------------------------------------


def test_ca3_ansicode_strip_drops_every_sgr() -> None:
    assert ansi_strip("\x1b[38;2;1;2;3mtc\x1b[0m") == "tc"
    assert ansi_strip("\x1b[mx") == "x"
    assert ansi_strip("\x1b[;31mx") == "x"


def test_ca3_colorcode_strip_drops_the_same_sequences() -> None:
    assert cc_strip("\x1b[38;2;1;2;3mtc\x1b[0m@R!") == "tc!"


# --- CA-1 and CA-2 stay for #533: these tests pin today's output ------------------------------


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("\x1b[31mred\x1b[0m plain", "@rred@w plain"),
        ("\x1b[1;37;44mhi", "@W@z4hi"),
        ("\x1b[1mbold", "@Wbold"),
        ("\x1b[91mbright", "@Rbright"),
        ("\x1b[22mhi", "hi"),
        ("\x1b[104mbg", "@z12bg"),
        ("\x1b[100mx", "@z8x"),
    ],
)
def test_ca1_ca2_resets_and_bold_convert(text: str, expected: str) -> None:
    """#533: a reset is ``@w``, and bold, bright and multi-part sequences keep their colour."""
    assert to_colorcode(text) == expected


def test_ca1_reset_round_trips_without_red_after_it() -> None:
    ansi = to_ansi(to_colorcode("\x1b[31mred\x1b[0m plain"))
    assert ansi == "\x1b[0;31mred\x1b[0;37m plain\x1b[0m"
    assert "31" not in ansi.split("red", 1)[1]


# --- cases found while building the tokenizer -------------------------------------------------


def test_letter_code_before_another_code_is_converted() -> None:
    assert to_ansi("@R@x075foo@w") == "\x1b[1;31m\x1b[38;5;075mfoo\x1b[0m"
    assert cc_strip("@R@x075foo@w") == "foo"


def test_background_code_before_a_letter_code_is_converted() -> None:
    assert to_ansi("@r@z165x") == "\x1b[0;31m\x1b[48;5;165mx\x1b[0m"
    assert cc_strip("@r@z165x") == "x"


def test_escape_then_dash_is_text() -> None:
    assert cc_strip("@@-") == "@-"


def test_trailing_at_is_kept() -> None:
    assert cc_strip("abc@") == "abc@"
    assert to_ansi("abc@") == "abc@"


def test_bare_xterm_letter_is_dropped() -> None:
    assert cc_strip("@x") == ""
    assert to_ansi("@x") == ""


def test_nul_is_ordinary_text() -> None:
    assert cc_strip("a\0b") == "a\0b"
    assert to_ansi("a\0b") == "a\0b"


def test_out_of_range_xterm_keeps_the_following_text() -> None:
    assert cc_strip("@x300a") == "a"
    assert to_ansi("@x300a") == "a"


def test_tilde_escape() -> None:
    assert cc_strip("a@-b") == "a~b"
    assert to_ansi("a@-b") == "a~b"


def test_strip_does_not_use_the_api() -> None:
    plugin = MagicMock()
    assert ColorsPlugin._api_colorcode_strip(plugin, "@Rfoo@w") == "foo"
    plugin.api.assert_not_called()


# --- byte equivalence with the code before the tokenizer --------------------------------------


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("@Rfoo@w", "\x1b[1;31mfoo\x1b[0m"),
        ("@wfoo", "\x1b[0;37mfoo\x1b[0m"),
        ("pre@Rfoo", "pre\x1b[1;31mfoo\x1b[0m"),
        ("@Rfoo@wbar", "\x1b[1;31mfoo\x1b[0;37mbar\x1b[0m"),
        ("@Rfoo@Gbar@w", "\x1b[1;31mfoo\x1b[1;32mbar\x1b[0m"),
        ("@x0751", "\x1b[38;5;075m1\x1b[0m"),
        ("@x2551", "\x1b[38;5;255m1\x1b[0m"),
        ("@z165@Rx@w", "\x1b[48;5;165m\x1b[1;31mx\x1b[0m"),
        ("no codes", "no codes"),
        ("\x1b[31mraw", "\x1b[31mraw"),
        ("@rx@w", "\x1b[0;31mx\x1b[0m"),
        ("@gx@w", "\x1b[0;32mx\x1b[0m"),
        ("@yx@w", "\x1b[0;33mx\x1b[0m"),
        ("@bx@w", "\x1b[0;34mx\x1b[0m"),
        ("@mx@w", "\x1b[0;35mx\x1b[0m"),
        ("@cx@w", "\x1b[0;36mx\x1b[0m"),
        ("@wx@w", "\x1b[0;37mx\x1b[0m"),
        ("@Dx@w", "\x1b[1;30mx\x1b[0m"),
        ("@Rx@w", "\x1b[1;31mx\x1b[0m"),
        ("@Gx@w", "\x1b[1;32mx\x1b[0m"),
        ("@Yx@w", "\x1b[1;33mx\x1b[0m"),
        ("@Bx@w", "\x1b[1;34mx\x1b[0m"),
        ("@Mx@w", "\x1b[1;35mx\x1b[0m"),
        ("@Cx@w", "\x1b[1;36mx\x1b[0m"),
        ("@Wx@w", "\x1b[1;37mx\x1b[0m"),
    ],
)
def test_to_ansicode_matches_the_previous_bytes(text: str, expected: str) -> None:
    assert to_ansi(text) == expected


# one SGR followed by "x"; the last three changed with #533 (reset, bold, multi-part)
ANSI_TO_COLORCODE = [
    ("\x1b[0;30mx", "@kx"),
    ("\x1b[0;31mx", "@rx"),
    ("\x1b[0;32mx", "@gx"),
    ("\x1b[0;33mx", "@yx"),
    ("\x1b[0;34mx", "@bx"),
    ("\x1b[0;35mx", "@mx"),
    ("\x1b[0;36mx", "@cx"),
    ("\x1b[0;37mx", "@wx"),
    ("\x1b[1;30mx", "@Dx"),
    ("\x1b[1;31mx", "@Rx"),
    ("\x1b[1;32mx", "@Gx"),
    ("\x1b[1;33mx", "@Yx"),
    ("\x1b[1;34mx", "@Bx"),
    ("\x1b[1;35mx", "@Mx"),
    ("\x1b[1;36mx", "@Cx"),
    ("\x1b[1;37mx", "@Wx"),
    ("\x1b[0mx", "x"),
    ("\x1b[40mx", "@z0x"),
    ("\x1b[41mx", "@z1x"),
    ("\x1b[42mx", "@z2x"),
    ("\x1b[43mx", "@z3x"),
    ("\x1b[44mx", "@z4x"),
    ("\x1b[45mx", "@z5x"),
    ("\x1b[46mx", "@z6x"),
    ("\x1b[47mx", "@z7x"),
    ("\x1b[30mx", "@kx"),
    ("\x1b[31mx", "@rx"),
    ("\x1b[32mx", "@gx"),
    ("\x1b[33mx", "@yx"),
    ("\x1b[34mx", "@bx"),
    ("\x1b[35mx", "@mx"),
    ("\x1b[36mx", "@cx"),
    ("\x1b[37mx", "@wx"),
    ("\x1b[01;31mx", "@Rx"),
    ("\x1b[0;31;40mx", "@r@z0x"),
]


@pytest.mark.parametrize(("text", "expected"), ANSI_TO_COLORCODE)
def test_ansicode_to_colorcode_matches_the_previous_result(text: str, expected: str) -> None:
    assert to_colorcode(text) == expected


def test_ansicode_to_colorcode_matches_for_every_xterm_code() -> None:
    for number in range(256):
        assert to_colorcode(f"\x1b[38;5;{number}mx") == f"@x{number}x"
        assert to_colorcode(f"\x1b[48;5;{number}mx") == f"@z{number}x"
    assert CONVERTANSI["38;5;255"] == "x255"


@pytest.mark.parametrize(
    ("text", "expected"),
    [("\x1b[38;2;1;2;3mx", "@x16x"), ("\x1b[mx", "x"), ("\x1b[;31mx", "@rx")],
)
def test_ansicode_to_colorcode_true_colour_and_empty_params(text: str, expected: str) -> None:
    assert to_colorcode(text) == expected


# --- the tokenize API -------------------------------------------------------------------------


def test_to_tokens_api_returns_raw_and_visible_pairs() -> None:
    pairs = ColorsPlugin._api_colorcode_to_tokens(MagicMock(), "@Rab@@\x1b[0m@-c@x")
    assert pairs == [
        ("@R", ""),
        ("ab", "ab"),
        ("@@", "@"),
        ("\x1b[0m", ""),
        ("@-", "~"),
        ("c", "c"),
        ("@x", ""),
    ]
    assert "".join(raw for raw, _ in pairs) == "@Rab@@\x1b[0m@-c@x"


# --- an @ directly before an escape sequence -----------------------------------------------


def test_at_before_sgr_is_text_and_the_sgr_is_stripped() -> None:
    """``@`` cannot start a code with the escape character, so it stays visible (#534)."""
    assert ansi_strip("@\x1b[31mx") == "@x"
    assert cc_strip("@\x1b[31mx") == "@x"


def test_at_before_sgr_converts_the_sgr() -> None:
    assert to_colorcode("@\x1b[31mx") == "@@rx"
