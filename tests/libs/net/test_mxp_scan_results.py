"""Tests for the data classes ``scan_modes`` and ``scan_definitions`` return (#426)."""

from collections.abc import Iterator

import pytest

from bastproxy.libs.net import mxp
from bastproxy.libs.net.mxp import DefinitionScan, MxpMode, MxpModes
from bastproxy.libs.net.protocols import PROTOCOLS
from bastproxy.libs.records import RMANAGER

ESC = "\x1b"
S, OP, L = MxpMode.SECURE, MxpMode.OPEN, MxpMode.LOCKED


@pytest.fixture(autouse=True)
def isolated(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    monkeypatch.setattr(RMANAGER, "record_instances", {})
    monkeypatch.setattr(RMANAGER, "records", {})
    PROTOCOLS.mud_disconnected()
    yield
    PROTOCOLS.mud_disconnected()


def test_the_results_are_slotted() -> None:
    modes = MxpModes(OP, OP)
    scan = DefinitionScan([], OP, OP, False)
    with pytest.raises(AttributeError):
        modes.extra = 1  # type: ignore[attr-defined]
    with pytest.raises(AttributeError):
        scan.extra = 1  # type: ignore[attr-defined]


def test_scan_modes_without_an_escape_keeps_the_modes() -> None:
    modes = mxp.scan_modes("x", OP, OP)
    assert isinstance(modes, MxpModes)
    assert modes.current == OP
    assert modes.default == OP


def test_scan_modes_secure_line() -> None:
    modes = mxp.scan_modes(f"{ESC}[1z", OP, OP)
    assert (modes.current, modes.default) == (S, OP)


def test_scan_modes_locked_default() -> None:
    modes = mxp.scan_modes(f"{ESC}[7z", OP, OP)
    assert (modes.current, modes.default) == (L, L)


def test_scan_modes_reset_after_a_secure_default() -> None:
    modes = mxp.scan_modes(f"{ESC}[6z{ESC}[3z", OP, OP)
    assert (modes.current, modes.default) == (OP, OP)


def test_scan_definitions_secure_tag() -> None:
    scan = mxp.scan_definitions(f"{ESC}[1z<!EL a>", OP, OP)
    assert isinstance(scan, DefinitionScan)
    assert scan.tags == ["<!EL a>"]
    assert (scan.current, scan.default) == (S, OP)
    assert scan.pending is False


def test_scan_definitions_trailing_temp_secure_is_pending() -> None:
    scan = mxp.scan_definitions(f"x{ESC}[4z", OP, OP)
    assert scan.tags == []
    assert scan.pending is True


def test_scan_definitions_pending_capture_takes_the_next_tag() -> None:
    scan = mxp.scan_definitions("<!EL b>", OP, OP, pending=True)
    assert scan.tags == ["<!EL b>"]
    assert scan.pending is False


@pytest.mark.parametrize(
    ("text", "current"),
    [(f"{ESC}[1z<!EL a><!EN b 'c'>", OP), ("<!EL a>", S), ("<!EL a>", L), (f"{ESC}[2z<!EL a>", S)],
)
def test_find_definitions_is_the_tags_of_scan_definitions(text: str, current: MxpMode) -> None:
    assert mxp.find_definitions(text, current, OP) == mxp.scan_definitions(text, current, OP).tags


def test_mxp_line_mode_carries_state_across_pieces() -> None:
    assert PROTOCOLS.mxp_line_mode(f"{ESC}[1zx", ended=False, enabled=True) is OP
    assert PROTOCOLS.mxp_line_mode("<!EL a>", ended=True, enabled=True) is S
    assert list(PROTOCOLS._mxp_defs.values()) == [["<!EL a>"]]
