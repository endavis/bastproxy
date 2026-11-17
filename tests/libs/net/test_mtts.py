"""Tests for the MTTS cycle and the MNES variables (#547)."""

import pytest

import bastproxy
from bastproxy.libs.net import mtts
from bastproxy.libs.net.mtts import MttsCapabilities, TtypeCycle

FIELDS = [
    "ansi",
    "vt100",
    "utf8",
    "colors_256",
    "mouse_tracking",
    "osc_color_palette",
    "screen_reader",
    "proxy",
    "truecolor",
    "mnes",
    "mslp",
    "ssl",
]


def test_proxy_bitvector_is_525() -> None:
    assert mtts.PROXY_CAPABILITIES.bitvector == 525
    assert 525 == 1 | 4 | 8 | 512


@pytest.mark.parametrize(("index", "field"), list(enumerate(FIELDS)))
def test_each_flag_has_its_spec_value(index: int, field: str) -> None:
    none = dict.fromkeys(FIELDS, False)
    caps = MttsCapabilities(**{**none, field: True})
    assert caps.bitvector == 2**index


def test_all_false_is_zero() -> None:
    assert MttsCapabilities(**dict.fromkeys(FIELDS, False)).bitvector == 0


def test_cycle_repeats_the_last_answer() -> None:
    cycle = TtypeCycle("BASTPROXY", "ANSI-256COLOR", 525)
    assert [cycle.next() for _ in range(5)] == [
        "BASTPROXY",
        "ANSI-256COLOR",
        "MTTS 525",
        "MTTS 525",
        "MTTS 525",
    ]


def test_reset_restarts_the_cycle() -> None:
    cycle = TtypeCycle("BASTPROXY", "ANSI-256COLOR", 525)
    for _ in range(3):
        cycle.next()
    cycle.reset()
    assert cycle.next() == "BASTPROXY"


def test_mnes_variables() -> None:
    variables = mtts.mnes_variables()
    assert set(variables) == {
        "CLIENT_NAME",
        "CLIENT_VERSION",
        "TERMINAL_TYPE",
        "MTTS",
        "CHARSET",
    }
    assert variables["CLIENT_NAME"] == "BASTPROXY"
    assert variables["CLIENT_VERSION"] == bastproxy.__version__
    assert variables["TERMINAL_TYPE"] == mtts.TERMINAL_TYPE
    assert variables["MTTS"] == "525"
    assert variables["CHARSET"] == "UTF-8"


def test_mnes_values_hold_no_reserved_bytes() -> None:
    reserved = {0, 1, 2, 3, 255}
    for value in mtts.mnes_variables().values():
        assert not reserved & set(value.encode())
