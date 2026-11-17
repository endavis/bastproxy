# Project: bastproxy
# Filename: libs/net/mtts.py
#
# File Description: the MTTS terminal type cycle and MNES variables sent to the MUD
#
# By: Bast
"""The proxy's answers to the MUD's TTYPE and NEW_ENVIRON requests (#547).

Two specifications describe what a MUD client tells a MUD about itself:

- MTTS, https://tintin.mudhalla.net/protocols/mtts/ : the MUD asks TTYPE repeatedly; the first
  answer is the client name, the second the terminal type and the third ``MTTS <bitvector>``.
- MNES, https://tintin.mudhalla.net/protocols/mnes/ : the same facts as NEW_ENVIRON variables.

The values describe the proxy itself, not any client: TTYPE is negotiated once, when the MUD
link is made, often before a client is attached, and clients come and go afterwards. The proxy
speaks UTF-8 to the MUD and has ANSI plus xterm-256 colour, so it reports ``MTTS 525``
(ANSI 1, UTF-8 4, 256 COLORS 8, MNES 512).

This module holds the pure logic and imports nothing from the plugins.
"""

# Standard Library
from dataclasses import dataclass

# Project
import bastproxy

CLIENT_NAME = "BASTPROXY"
TERMINAL_TYPE = "ANSI-256COLOR"
CHARSET = "UTF-8"


@dataclass(frozen=True)
class MttsCapabilities:
    """The MTTS capability flags, one field for each bit of the specification."""

    ansi: bool = True  # 1
    vt100: bool = False  # 2
    utf8: bool = True  # 4
    colors_256: bool = True  # 8
    mouse_tracking: bool = False  # 16
    osc_color_palette: bool = False  # 32
    screen_reader: bool = False  # 64
    proxy: bool = False  # 128
    truecolor: bool = False  # 256
    mnes: bool = True  # 512
    mslp: bool = False  # 1024
    ssl: bool = False  # 2048

    @property
    def bitvector(self) -> int:
        """Return the flags as the MTTS bit vector."""
        flags = (
            self.ansi,
            self.vt100,
            self.utf8,
            self.colors_256,
            self.mouse_tracking,
            self.osc_color_palette,
            self.screen_reader,
            self.proxy,
            self.truecolor,
            self.mnes,
            self.mslp,
            self.ssl,
        )
        return sum(1 << bit for bit, on in enumerate(flags) if on)


PROXY_CAPABILITIES = MttsCapabilities()


class TtypeCycle:
    """Answer successive TTYPE requests: client name, terminal type, then ``MTTS <bits>``."""

    def __init__(self, client_name: str, terminal_type: str, mtts: int) -> None:
        """Create a cycle at its first step."""
        self.client_name = client_name
        self.terminal_type = terminal_type
        self.mtts = mtts
        self._step = 0

    def next(self) -> str:
        """Return the answer for the next request; the last answer repeats."""
        step = self._step
        self._step += 1
        if step == 0:
            return self.client_name
        if step == 1:
            return self.terminal_type
        return f"MTTS {self.mtts}"

    def reset(self) -> None:
        """Start again at the client name."""
        self._step = 0


def mnes_variables() -> dict[str, str]:
    """Return the MNES variables the proxy answers."""
    return {
        "CLIENT_NAME": CLIENT_NAME,
        "CLIENT_VERSION": bastproxy.__version__,
        "TERMINAL_TYPE": TERMINAL_TYPE,
        "MTTS": str(PROXY_CAPABILITIES.bitvector),
        "CHARSET": CHARSET,
    }
