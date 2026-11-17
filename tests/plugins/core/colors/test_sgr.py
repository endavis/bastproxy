"""Unit tests for the SGR state machine behind ``ansicode.to.colorcode`` (#533)."""

import logging

import pytest

from bastproxy.plugins.core.colors.libs._sgr import (
    DEFAULT_STATE,
    MAX_SGR_PARAMS,
    SgrState,
    apply_sgr,
    diff_codes,
    rgb_to_xterm,
    sgr_to_colorcode,
)


@pytest.mark.parametrize(
    ("rgb", "expected"),
    [
        ((0, 0, 0), 16),
        ((255, 255, 255), 231),
        ((8, 8, 8), 232),
        ((1, 2, 3), 16),
        ((255, 0, 0), 196),
        ((128, 128, 128), 244),
    ],
)
def test_rgb_to_xterm(rgb: tuple[int, int, int], expected: int) -> None:
    assert rgb_to_xterm(*rgb) == expected


@pytest.mark.parametrize(
    ("params", "expected"),
    [
        ("0", DEFAULT_STATE),
        ("", DEFAULT_STATE),
        ("1", (None, True, None)),
        ("1;22", DEFAULT_STATE),
        ("31", (("b", 1), False, None)),
        ("91", (("B", 1), False, None)),
        ("31;39", DEFAULT_STATE),
        ("44", (None, False, 4)),
        ("104", (None, False, 12)),
        ("44;49", DEFAULT_STATE),
        ("38;5;200", (("x", 200), False, None)),
        ("48;5;7", (None, False, 7)),
        ("38;2;255;0;0", (("x", 196), False, None)),
        ("48;2;128;128;128", (None, False, 244)),
        ("4;7;31", (("b", 1), False, None)),
        ("38;5;300", DEFAULT_STATE),
        ("31;38;5", (("b", 1), False, None)),
    ],
)
def test_apply_sgr(params: str, expected: SgrState) -> None:
    assert apply_sgr(DEFAULT_STATE, params) == expected


def test_malformed_extended_colour_is_debug_logged_only(
    caplog: pytest.LogCaptureFixture,
) -> None:
    with caplog.at_level(logging.DEBUG):
        apply_sgr(DEFAULT_STATE, "38;5;999")
    assert not [r for r in caplog.records if r.levelno >= logging.WARNING]


@pytest.mark.parametrize(
    ("emitted", "target", "expected"),
    [
        (DEFAULT_STATE, DEFAULT_STATE, ""),
        (DEFAULT_STATE, (("b", 1), False, None), "@r"),
        ((("b", 1), False, None), (("b", 1), True, None), "@R"),
        ((("b", 1), True, None), (("b", 1), False, None), "@r"),
        ((("b", 1), False, None), DEFAULT_STATE, "@w"),
        ((None, True, None), DEFAULT_STATE, "@w"),
        ((("b", 1), False, 4), (None, False, 4), "@w@z4"),
        ((("b", 1), False, 4), (("b", 1), False, None), "@w@r"),
        (DEFAULT_STATE, (None, True, 4), "@W@z4"),
    ],
)
def test_diff_codes(emitted: SgrState, target: SgrState, expected: str) -> None:
    assert diff_codes(emitted, target) == expected


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("plain", "plain"),
        ("\x1b[31ma\x1b[31mb", "@rab"),
        ("\x1b[0m\x1b[31m", ""),
        ("\x1b[31mx\x1b[0m", "@rx"),
        ("\x1b[0;37mYour", "@wYour"),
        ("\x1b[1m\x1b[31mx", "@Rx"),
        ("\x1b[1;31mR\x1b[22mr", "@RR@rr"),
        ("\x1b[1mb\x1b[22mx", "@Wb@wx"),
        ("\x1b[31mr\x1b[39mx", "@rr@wx"),
        ("\x1b[31;44mr\x1b[39mx", "@r@z4r@w@z4x"),
        ("\x1b[31;44mr\x1b[49mx", "@r@z4r@w@rx"),
        ("\x1b[4;31mx", "@rx"),
        ("\x1b[7mx", "x"),
        ("\x1b[38;5;300mx", "x"),
        ("\x1b[38;5mx\x1b[32my", "x@gy"),
        ("a\x1b[31m\x1b[0mb", "ab"),
    ],
)
def test_sgr_to_colorcode(text: str, expected: str) -> None:
    assert sgr_to_colorcode(text) == expected


def test_overlong_parameter_is_ignored() -> None:
    """A parameter of more than three digits is no SGR code; the rest still applies (#533)."""
    assert sgr_to_colorcode("\x1b[" + "9" * 5000 + ";31mx") == "@rx"


def test_leading_zeros_do_not_count_as_digits() -> None:
    assert sgr_to_colorcode("\x1b[00031mx") == "@rx"


def test_many_leading_zeros_are_read_as_the_value() -> None:
    assert sgr_to_colorcode("\x1b[" + "0" * 5000 + "31mx") == "@rx"
    assert sgr_to_colorcode("\x1b[" + "0" * 5000 + "mx") == "x"


def test_overlong_extended_colour_value_is_malformed() -> None:
    assert sgr_to_colorcode("\x1b[38;5;" + "1" * 10 + "mx") == "x"


def test_parameters_beyond_the_limit_are_ignored() -> None:
    """Only the first MAX_SGR_PARAMS parameters of one sequence are read (#533)."""
    filler = ";".join(["4"] * (MAX_SGR_PARAMS - 1))
    assert sgr_to_colorcode(f"\x1b[{filler};31mx") == "@rx"
    assert sgr_to_colorcode(f"\x1b[{filler};4;31mx") == "x"
    many = ";".join(["38;5;1"] * 1000) + ";32"
    assert sgr_to_colorcode(f"\x1b[{many}mx") == "@x1x"
