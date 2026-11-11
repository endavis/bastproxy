# Project: bastproxy
# Filename: libs/net/mxp.py
#
# File Description: MXP line modes, a bounded tag stripper and the per-client rendering of a line
#
# By: Bast
"""MXP helpers: line modes, a bounded tag stripper and per-client rendering (#61, ADR-0001).

MXP markup is ordinary text inside the data stream. The proxy passes it to a client that
negotiated MXP and strips it for a client that did not, and for triggers.

Modes: the MUD sets the line mode with the escape ``ESC[<n>z``. ``0`` (open), ``1`` (secure),
``2`` (locked) and ``4`` (temporary secure) last to the end of the line. ``3`` resets the
default mode to open, and ``5``, ``6`` and ``7`` set the default to open, secure or locked. At
the end of a line the mode returns to the default. Stripping tells only locked (text is
literal) from not locked (every well-formed tag is removed).

``strip`` runs in one forward pass that never steps back. It removes the mode escapes and the
well-formed tags, and decodes the entities ``&lt;``, ``&gt;``, ``&amp;``, ``&quot;`` and decimal
``&#NNN;``. A ``<`` that does not start a tag (``HP < 50``), a tag with no closing ``>`` and
any other entity stay as written. ANSI colour codes are kept.

The limits are module constants, so a test can monkeypatch them:

- ``MXP_MAX_TAG_LENGTH``: a ``<`` with no ``>`` within that many characters stays literal.
- ``MXP_MAX_ENTITY_LENGTH``: an ``&`` with no ``;`` within that many characters stays literal.

Each ``<`` looks ahead at most ``MXP_MAX_TAG_LENGTH`` characters, so the work for a line is
proportional to its length times that constant at most.
"""

# Standard Library
import re
from enum import StrEnum
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from bastproxy.libs.records.rtypes.networkdata import NetworkDataLine

__all__ = [
    "LOCKED_LINE",
    "MXP_MAX_ENTITY_LENGTH",
    "MXP_MAX_TAG_LENGTH",
    "MxpMode",
    "apply_escape",
    "render_for_client",
    "scan_modes",
    "strip",
    "sync_escape",
]

MXP_MAX_TAG_LENGTH = 2048
MXP_MAX_ENTITY_LENGTH = 32
_MAX_ESCAPE_DIGITS = 6

LOCKED_LINE = "\x1b[2z"

_SPECIAL_RE = re.compile(r"[<&\x1b]")
_ENTITIES = {"lt": "<", "gt": ">", "amp": "&", "quot": '"'}


class MxpMode(StrEnum):
    """The MXP mode of a line."""

    OPEN = "open"
    SECURE = "secure"
    LOCKED = "locked"


def apply_escape(n: int, current: MxpMode, default: MxpMode) -> tuple[MxpMode, MxpMode]:
    """Apply the mode escape ``ESC[<n>z``; returns the new ``(current, default)``.

    An unknown number changes nothing.
    """
    if n == 0:
        return MxpMode.OPEN, default
    if n in (1, 4):
        return MxpMode.SECURE, default
    if n == 2:
        return MxpMode.LOCKED, default
    if n == 3:
        return MxpMode.OPEN, MxpMode.OPEN
    if n == 5:
        return MxpMode.OPEN, MxpMode.OPEN
    if n == 6:
        return MxpMode.SECURE, MxpMode.SECURE
    if n == 7:
        return MxpMode.LOCKED, MxpMode.LOCKED
    return current, default


def _escape_at(text: str, i: int) -> tuple[int, int] | None:
    """If ``ESC[<digits>z`` starts at ``i``, return ``(number, end index)``, else None."""
    if text[i + 1 : i + 2] != "[":
        return None
    j = i + 2
    limit = min(len(text), j + _MAX_ESCAPE_DIGITS + 1)
    while j < limit and text[j].isascii() and text[j].isdigit():
        j += 1
    if j == i + 2 or j - (i + 2) > _MAX_ESCAPE_DIGITS or text[j : j + 1] != "z":
        return None
    return int(text[i + 2 : j]), j + 1


def scan_modes(text: str, current: MxpMode, default: MxpMode) -> tuple[MxpMode, MxpMode]:
    """Apply every mode escape in ``text`` in order; returns the final ``(current, default)``."""
    pos = text.find("\x1b")
    while pos != -1:
        found = _escape_at(text, pos)
        if found is not None:
            current, default = apply_escape(found[0], current, default)
            pos = text.find("\x1b", found[1])
        else:
            pos = text.find("\x1b", pos + 1)
    return current, default


def _tag_end(text: str, start: int, last_gt: int) -> int:
    """Return the index just past the tag that starts at ``start``, or -1 when it is not a tag.

    The tag ends at the first ``>`` outside a ``'...'`` or ``"..."`` value, within
    ``MXP_MAX_TAG_LENGTH`` characters.
    """
    if start >= last_gt:
        return -1
    window_end = min(len(text), start + MXP_MAX_TAG_LENGTH)
    first = text.find(">", start + 1, window_end)
    if first == -1:
        return -1
    segment = text[start + 1 : first]
    if "'" not in segment and '"' not in segment:
        return first + 1
    quote = ""
    for k in range(start + 1, window_end):
        ch = text[k]
        if quote:
            if ch == quote:
                quote = ""
        elif ch in "'\"":
            quote = ch
        elif ch == ">":
            return k + 1
    return -1


def _entity_at(text: str, i: int) -> tuple[str, int] | None:
    """If a decodable entity starts at ``i``, return ``(character, end index)``, else None."""
    end = text.find(";", i + 1, i + 2 + MXP_MAX_ENTITY_LENGTH)
    if end == -1:
        return None
    name = text[i + 1 : end]
    if name in _ENTITIES:
        return _ENTITIES[name], end + 1
    if name.startswith("#") and len(name) > 1:
        digits = name[1:]
        if digits.isascii() and digits.isdigit() and len(digits) <= 7:
            code = int(digits)
            if 32 <= code <= 0x10FFFF and not 127 <= code <= 159 and not 0xD800 <= code <= 0xDFFF:
                return chr(code), end + 1
    return None


def strip(text: str, mode: MxpMode | str = MxpMode.OPEN) -> str:
    """Remove the MXP markup from ``text``, a line that starts in ``mode``.

    Mode escapes are always removed. Outside locked mode, well-formed tags are removed and the
    standard entities are decoded; in locked mode they stay as written. A mode escape in the
    middle of the line applies from that point on.
    """
    if "<" not in text and "&" not in text and "\x1b" not in text:
        return text
    locked = mode == MxpMode.LOCKED
    last_gt = text.rfind(">")
    out: list[str] = []
    pos = 0
    size = len(text)
    while pos < size:
        match = _SPECIAL_RE.search(text, pos)
        if match is None:
            out.append(text[pos:])
            break
        i = match.start()
        out.append(text[pos:i])
        ch = text[i]
        pos = i + 1
        if ch == "\x1b":
            found = _escape_at(text, i)
            if found is None:
                out.append(ch)
                continue
            current, _ = apply_escape(
                found[0], MxpMode.LOCKED if locked else MxpMode.OPEN, MxpMode.OPEN
            )
            locked = current == MxpMode.LOCKED
            pos = found[1]
        elif locked:
            out.append(ch)
        elif ch == "<":
            nxt = text[i + 1 : i + 2]
            end = _tag_end(text, i, last_gt) if nxt and (nxt.isalpha() or nxt in "/!") else -1
            if end == -1:
                out.append(ch)
            else:
                pos = end
        else:
            decoded = _entity_at(text, i)
            if decoded is None:
                out.append(ch)
            else:
                out.append(decoded[0])
                pos = decoded[1]
    return "".join(out)


def sync_escape(default: MxpMode) -> str:
    """The escape that tells a newly joined MXP client the MUD's default mode, or ``""``.

    Nothing is needed while the default is open, since that is where a client starts.
    """
    if default == MxpMode.SECURE:
        return "\x1b[6z"
    if default == MxpMode.LOCKED:
        return "\x1b[7z"
    return ""


def render_for_client(line: "NetworkDataLine", client_mxp: bool) -> str | bytes:
    """The text to write to one client for ``line``.

    Telnet-command lines and lines that are not IO pass through unchanged. A line with
    ``mxp_mode`` set came from a MUD with MXP: an MXP client gets it as it is, any other client
    gets it stripped. A line with no ``mxp_mode`` is plain text the proxy made (or came from a
    MUD without MXP): an MXP client gets it behind ``ESC[2z`` so it shows as literal text, and any
    other client gets it as it is.
    """
    text = line.line
    if line.is_command_telnet or not line.is_io or not isinstance(text, str):
        return text
    if line.mxp_mode is None:
        return LOCKED_LINE + text if client_mxp else text
    return text if client_mxp else strip(text, line.mxp_mode)
