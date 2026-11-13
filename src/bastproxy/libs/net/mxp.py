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
- ``MXP_SCAN_FACTOR``: the look-ahead limit for a whole line, per character of the line.

Each ``<`` looks ahead at most ``MXP_MAX_TAG_LENGTH`` characters, and the look-ahead for a
whole line is limited to ``MXP_SCAN_FACTOR`` times its length plus ``MXP_MAX_TAG_LENGTH``.
Once a line has used that, every later ``<`` in it stays literal. A well-formed line looks
ahead about once over each tag, far below the limit, so the work for any line stays
proportional to its length.

``find_definitions`` collects the element, entity, attribute-list and tag definitions
(``<!EL>``, ``<!EN>``, ``<!AT>``, ``<!TAG>`` and their long forms) that the MUD sent in secure
mode, so the proxy can replay them to an MXP client that joins later (#333). It runs in one
forward pass under the same ``MXP_SCAN_FACTOR`` look-ahead limit as ``strip``. ``ESC[4z`` covers
only the next well-formed tag. ``definition_key`` names a definition by kind and name in one
forward pass over the tag. The stored count and size are limited by ``MXP_MAX_DEFINITIONS`` and
``MXP_MAX_DEFINITION_CHARS``.

Text the proxy sends to an MXP client as literal text (``render_for_client`` with no
``mxp_mode``) has its own mode escapes removed and every line in it locked, so nothing in it
can turn MXP back on.
"""

# Standard Library
import re
from dataclasses import dataclass
from enum import StrEnum
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from bastproxy.libs.records.rtypes.networkdata import NetworkDataLine

__all__ = [
    "LOCKED_LINE",
    "MXP_MAX_DEFINITIONS",
    "MXP_MAX_DEFINITION_CHARS",
    "MXP_MAX_ENTITY_LENGTH",
    "MXP_MAX_TAG_LENGTH",
    "MXP_SCAN_FACTOR",
    "DefinitionScan",
    "MxpMode",
    "MxpModes",
    "apply_escape",
    "definition_key",
    "find_definitions",
    "render_for_client",
    "scan_definitions",
    "scan_modes",
    "strip",
    "sync_escape",
]

MXP_MAX_TAG_LENGTH = 2048
MXP_MAX_ENTITY_LENGTH = 32
MXP_SCAN_FACTOR = 2
MXP_MAX_DEFINITIONS = 256
MXP_MAX_DEFINITION_CHARS = 65536
_MAX_ESCAPE_DIGITS = 6

LOCKED_LINE = "\x1b[2z"

_SPECIAL_RE = re.compile(r"[<&\x1b]")
_ANY_MODE_ESCAPE_RE = re.compile(r"\x1b\[[0-9]*z")
# An ESC that does not start a CSI sequence ending in a letter other than ``z``.
_OTHER_ESC_RE = re.compile(r"\x1b(?!\[[0-9;?]*[A-Za-y])")
# A line end that is not the last character: ``\n``, or ``\r`` not followed by ``\n``.
_LINE_END_RE = re.compile(r"(\n|\r(?!\n))(?!\Z)")
_DEFINITION_SPECIAL_RE = re.compile(r"[<\x1b]")
_DEFINITION_KINDS = {
    "ELEMENT": "ELEMENT",
    "EL": "ELEMENT",
    "ENTITY": "ENTITY",
    "EN": "ENTITY",
    "ATTLIST": "ATTLIST",
    "AT": "ATTLIST",
    "TAG": "TAG",
}
_ENTITIES = {"lt": "<", "gt": ">", "amp": "&", "quot": '"'}


class MxpMode(StrEnum):
    """The MXP mode of a line."""

    OPEN = "open"
    SECURE = "secure"
    LOCKED = "locked"


@dataclass(slots=True)
class MxpModes:
    """The line mode state after a scan of mode escapes.

    Attributes:
        current: The mode of the line at the end of the scanned text.
        default: The MUD's default mode at the end of the scanned text.
    """

    current: MxpMode
    default: MxpMode


@dataclass(slots=True)
class DefinitionScan:
    """The result of ``scan_definitions``: the tags found and the capture state after them.

    Attributes:
        tags: The definition tags found in secure mode, in order.
        current: The capture mode at the end of the scanned text.
        default: The MUD's default mode at the end of the scanned text.
        pending: True only when ``ESC[4z`` was the last thing in the scanned text.
    """

    tags: list[str]
    current: MxpMode
    default: MxpMode
    pending: bool


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


def scan_modes(text: str, current: MxpMode, default: MxpMode) -> MxpModes:
    """Apply every mode escape in ``text`` in order; returns the final modes as ``MxpModes``."""
    pos = text.find("\x1b")
    while pos != -1:
        found = _escape_at(text, pos)
        if found is not None:
            current, default = apply_escape(found[0], current, default)
            pos = text.find("\x1b", found[1])
        else:
            pos = text.find("\x1b", pos + 1)
    return MxpModes(current, default)


def _tag_end(text: str, start: int, last_gt: int, budget: int) -> tuple[int, int]:
    """Find the end of the tag that starts at ``start``.

    Returns ``(end, used)``: ``end`` is the index just past the tag, or -1 when it is not a
    tag, and ``used`` is how many characters the look-ahead covered. The tag ends at the first
    ``>`` outside a ``'...'`` or ``"..."`` value, within ``MXP_MAX_TAG_LENGTH`` characters and
    within ``budget`` characters.
    """
    if start >= last_gt or budget <= 0:
        return -1, 0
    window_end = min(len(text), start + 1 + min(MXP_MAX_TAG_LENGTH, budget))
    first = text.find(">", start + 1, window_end)
    if first == -1:
        return -1, window_end - start - 1
    segment = text[start + 1 : first]
    if "'" not in segment and '"' not in segment:
        return first + 1, first - start
    quote = ""
    for k in range(start + 1, window_end):
        ch = text[k]
        if quote:
            if ch == quote:
                quote = ""
        elif ch in "'\"":
            quote = ch
        elif ch == ">":
            return k + 1, k - start
    return -1, window_end - start - 1


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
    budget = MXP_SCAN_FACTOR * size + MXP_MAX_TAG_LENGTH
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
            end = -1
            if nxt and (nxt.isalpha() or nxt in "/!"):
                end, used = _tag_end(text, i, last_gt, budget)
                budget -= used
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


def _split_words(body: str) -> list[tuple[str, bool]]:
    """Split ``body`` on whitespace outside quotes, in one forward pass.

    Returns ``(word without its quote characters, word had a quote)`` pairs.
    """
    words: list[tuple[str, bool]] = []
    chars: list[str] = []
    quote = ""
    quoted = False
    in_word = False
    for ch in body:
        if quote:
            if ch == quote:
                quote = ""
            else:
                chars.append(ch)
        elif ch in "'\"":
            quote = ch
            quoted = True
            in_word = True
        elif ch.isspace():
            if in_word:
                words.append(("".join(chars), quoted))
                chars = []
                quoted = False
                in_word = False
        else:
            chars.append(ch)
            in_word = True
    if in_word:
        words.append(("".join(chars), quoted))
    return words


def definition_key(tag: str) -> tuple[tuple[str, str], str] | None:
    """Name the definition a ``<!KIND name ...>`` tag makes, or None for any other tag.

    Returns ``((kind, name), action)``. The kind is the full kind (``ELEMENT``, ``ENTITY``,
    ``ATTLIST`` or ``TAG``). Element, attribute-list and tag names are casefolded, entity names
    keep their case. The action is ``delete`` for a bare ``DELETE`` word after the name, ``add``
    for a bare ``ADD`` or ``REMOVE`` word in an entity definition, else ``set``.
    """
    if not tag.startswith("<!") or not tag.endswith(">"):
        return None
    words = _split_words(tag[2:-1])
    if len(words) < 2 or words[0][1]:
        return None
    kind = _DEFINITION_KINDS.get(words[0][0].upper())
    name = words[1][0]
    if kind is None or not name:
        return None
    action = "set"
    for word, quoted in words[2:]:
        if quoted:
            continue
        upper = word.upper()
        if upper == "DELETE":
            action = "delete"
            break
        if upper in ("ADD", "REMOVE") and kind == "ENTITY":
            action = "add"
    return (kind, name if kind == "ENTITY" else name.casefold()), action


def find_definitions(text: str, current: MxpMode, default: MxpMode) -> list[str]:
    """The definition tags in ``text`` that were sent in secure mode (see ``scan_definitions``)."""
    return scan_definitions(text, current, default).tags


def scan_definitions(
    text: str, current: MxpMode, default: MxpMode, pending: bool = False
) -> DefinitionScan:
    """Find the definition tags in ``text`` sent in secure mode, and the capture state after it.

    ``text`` is a piece of a line that starts in ``current`` with the MUD's ``default``.
    ``pending`` is True when the previous piece ended right after ``ESC[4z``. A tag counts when
    the mode is secure, or it is the tag that starts at the ``<`` immediately after ``ESC[4z``
    (temporary secure covers only that one tag, as an MXP client applies it). ``ESC[4z`` never
    changes ``current`` here, unlike ``apply_escape`` for stripping. One forward pass, under the
    same look-ahead limit as ``strip``. A tag with a line break or an ESC in it is skipped.

    Returns a ``DefinitionScan`` (``tags``, ``current``, ``default``, ``pending``): the state to carry into the next piece of the
    same line. ``pending`` is True only when ``ESC[4z`` was the last thing in ``text``.
    """
    found: list[str] = []
    last_gt = text.rfind(">")
    pos = 0
    size = len(text)
    budget = MXP_SCAN_FACTOR * size + MXP_MAX_TAG_LENGTH
    if pending and size and text[0] != "<":
        pending = False
    while pos < size:
        match = _DEFINITION_SPECIAL_RE.search(text, pos)
        if match is None:
            break
        i = match.start()
        pos = i + 1
        if text[i] == "\x1b":
            esc = _escape_at(text, i)
            if esc is None:
                continue
            pos = esc[1]
            if esc[0] == 4:
                # Temporary secure applies only when the very next character is ``<``; at the
                # end of the piece it carries over to the next piece of the line.
                pending = pos >= size or text[pos] == "<"
            else:
                pending = False
                current, default = apply_escape(esc[0], current, default)
            continue
        temp = pending
        pending = False
        if current == MxpMode.LOCKED and not temp:
            continue
        nxt = text[i + 1 : i + 2]
        if not nxt or not (nxt.isalpha() or nxt in "/!"):
            continue
        end, used = _tag_end(text, i, last_gt, budget)
        budget -= used
        if end == -1:
            continue
        pos = end
        secure = temp or current == MxpMode.SECURE
        tag = text[i:end]
        if (
            secure
            and nxt == "!"
            and definition_key(tag) is not None
            and not any(c in tag for c in "\r\n\x1b")
        ):
            found.append(tag)
    return DefinitionScan(found, current, default, pending)


def sync_escape(default: MxpMode) -> str:
    """The escape that tells a newly joined MXP client the MUD's default mode, or ``""``.

    Nothing is needed while the default is open, since that is where a client starts.
    """
    if default == MxpMode.SECURE:
        return "\x1b[6z"
    if default == MxpMode.LOCKED:
        return "\x1b[7z"
    return ""


def _literal_text(text: str) -> str:
    """``text`` with its mode escapes removed, for an MXP client to show as literal text.

    Whole ``ESC[<n>z`` escapes are removed first. Then every ESC that does not start a CSI
    sequence ending in a letter other than ``z`` is dropped. That second pass only removes ESC
    characters, so it cannot form a new escape, and an escape left over from nesting
    (``ESC[ESC[0zz``) loses its ESC. ANSI colour codes are kept.
    """
    return _OTHER_ESC_RE.sub("", _ANY_MODE_ESCAPE_RE.sub("", text))


def render_for_client(line: "NetworkDataLine", client_mxp: bool) -> str | bytes:
    """The text to write to one client for ``line``.

    Telnet-command lines and lines that are not IO pass through unchanged. A line with
    ``mxp_mode`` set came from a MUD with MXP: an MXP client gets it as it is, any other client
    gets it stripped. A line with no ``mxp_mode`` is plain text the proxy made (or came from a
    MUD without MXP): an MXP client gets it behind ``ESC[2z`` so it shows as literal text, and any
    other client gets it as it is. For an MXP client its own mode escapes are removed
    (``_literal_text``) and every line in it is locked, including a line after a lone ``\r``,
    so nothing in it can turn MXP back on.
    """
    text = line.line
    if line.is_command_telnet or not line.is_io or not isinstance(text, str):
        return text
    if line.mxp_mode is None:
        if not client_mxp:
            return text
        return LOCKED_LINE + _LINE_END_RE.sub(r"\1" + LOCKED_LINE, _literal_text(text))
    return text if client_mxp else strip(text, line.mxp_mode)
