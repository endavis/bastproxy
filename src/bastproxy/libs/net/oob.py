# Project: bastproxy
# Filename: libs/net/oob.py
#
# File Description: bounded codecs for the out-of-band protocols GMCP, MSDP and MSSP
#
# By: Bast
"""Bounded decoders and helpers for GMCP, MSDP and MSSP (#59, #60, ADR-0001).

The proxy decodes GMCP, MSDP and MSSP itself, on links where the option was negotiated, with the
decoders here. Every decoder checks a size limit first and runs in one pass over the payload,
so the work for a message is proportional to its length. A message that does not decode raises
``OobDecodeError``; the caller drops that message and keeps the link open.

The limits are module constants, so a test can monkeypatch them.
"""

# Standard Library
import json
import re
from collections.abc import Iterable
from typing import Any

# 3rd Party
from telnetlib3.mud import mssp_decode
from telnetlib3.telopt import (
    MSDP_ARRAY_CLOSE,
    MSDP_ARRAY_OPEN,
    MSDP_TABLE_CLOSE,
    MSDP_TABLE_OPEN,
    MSDP_VAL,
    MSDP_VAR,
)

# Project
from bastproxy.libs.logger import get_logger

logger = get_logger(__name__)

__all__ = [
    "CACHE_MAX_ENTRIES",
    "CLIENT_MAX_MODULES",
    "MSDP_MAX_DEPTH",
    "MSDP_MAX_NODES",
    "MSSP_MAX_VALUES",
    "MSSP_MAX_VALUE_LEN",
    "MSSP_MAX_VARIABLES",
    "OOB_MAX_PAYLOAD",
    "REDACTED",
    "OobDecodeError",
    "decode_gmcp",
    "decode_msdp",
    "decode_mssp",
    "is_credential_package",
    "merge_gmcp",
    "package_wanted",
    "parse_supports",
    "redact_gmcp_payload",
    "supports_payload",
    "valid_mssp_name",
    "valid_package",
    "valid_variable",
]

REDACTED = "<redacted>"

OOB_MAX_PAYLOAD = 256 * 1024
MSDP_MAX_DEPTH = 16
MSDP_MAX_NODES = 4096
CACHE_MAX_ENTRIES = 512
CLIENT_MAX_MODULES = 64
MSSP_MAX_VARIABLES = 256
MSSP_MAX_VALUES = 64
MSSP_MAX_VALUE_LEN = 4096

_PACKAGE_RE = re.compile(r"^[A-Za-z][A-Za-z0-9_.-]{0,63}$")
_VARIABLE_RE = re.compile(r"^[A-Za-z0-9_]{1,64}$")
_MSSP_NAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_ .-]{0,63}$")
_MODULE_RE = re.compile(r"^([A-Za-z][A-Za-z0-9_.]{0,63})(?: ([0-9]{1,3}))?$")

_MSDP_DELIMITERS = frozenset(
    byte[0] for byte in (MSDP_VAR, MSDP_VAL, MSDP_TABLE_CLOSE, MSDP_ARRAY_CLOSE)
)
_MSDP_VAR = MSDP_VAR[0]
_MSDP_VAL = MSDP_VAL[0]
_MSDP_TABLE_OPEN = MSDP_TABLE_OPEN[0]
_MSDP_TABLE_CLOSE = MSDP_TABLE_CLOSE[0]
_MSDP_ARRAY_OPEN = MSDP_ARRAY_OPEN[0]
_MSDP_ARRAY_CLOSE = MSDP_ARRAY_CLOSE[0]


class OobDecodeError(ValueError):
    """A GMCP, MSDP or MSSP payload that does not decode within the limits.

    ``name`` is the package or variable name when it was read before the failure.
    """

    def __init__(self, message: str, name: str | None = None) -> None:
        """Create the error with its reason and, when known, the name it concerns."""
        super().__init__(message)
        self.name = name


def valid_package(package: str) -> bool:
    """Whether ``package`` is an acceptable GMCP package name."""
    return _PACKAGE_RE.fullmatch(package) is not None


def valid_variable(variable: str) -> bool:
    """Whether ``variable`` is an acceptable MSDP variable name."""
    return _VARIABLE_RE.fullmatch(variable) is not None


def valid_mssp_name(name: str) -> bool:
    """Whether ``name`` is an acceptable MSSP variable name (spaces allowed, as in CRAWL DELAY)."""
    return _MSSP_NAME_RE.fullmatch(name) is not None


def decode_gmcp(payload: bytes, encoding: str = "utf-8") -> tuple[str, Any]:
    """Decode a GMCP payload into ``(package, data)``.

    The payload is ``Package.Name`` optionally followed by a space and JSON. A missing or blank
    body gives ``None`` for the data.

    Raises:
        OobDecodeError: If the payload is over ``OOB_MAX_PAYLOAD``, the package name is not
            valid, or the body is not JSON.

    """
    if len(payload) > OOB_MAX_PAYLOAD:
        msg = "GMCP payload over the size limit"
        raise OobDecodeError(msg)
    text = payload.decode(encoding, errors="replace")
    package, _, body = text.partition(" ")
    if not valid_package(package):
        msg = "GMCP package name is not valid"
        raise OobDecodeError(msg)
    body = body.strip()
    if not body:
        return package, None
    try:
        return package, json.loads(body)
    except (ValueError, RecursionError) as exc:
        msg = "GMCP body is not valid JSON"
        raise OobDecodeError(msg, name=package) from exc


class _MsdpFrame:
    """One open MSDP container: a table or array being filled, plus the key a value is for."""

    __slots__ = ("container", "key")

    def __init__(self, container: dict[str, Any] | list[Any]) -> None:
        self.container = container
        self.key: str | None = None


def decode_msdp(payload: bytes, encoding: str = "utf-8") -> dict[str, Any]:
    """Decode an MSDP payload into a dict of variable name to value.

    A value is a string, a list (``ARRAY_OPEN``) or a dict (``TABLE_OPEN``). The decoder walks
    the payload once with an explicit stack and consumes at least one byte per step.

    Raises:
        OobDecodeError: If the payload is empty, over ``OOB_MAX_PAYLOAD``, malformed or
            truncated, nests deeper than ``MSDP_MAX_DEPTH``, has more than ``MSDP_MAX_NODES``
            values, or has a top level variable name that is not valid.

    """
    size = len(payload)
    if size > OOB_MAX_PAYLOAD:
        msg = "MSDP payload over the size limit"
        raise OobDecodeError(msg)
    if size == 0:
        msg = "MSDP payload is empty"
        raise OobDecodeError(msg)

    top: dict[str, Any] = {}
    stack: list[_MsdpFrame] = [_MsdpFrame(top)]
    nodes = 0
    last_name: str | None = None
    i = 0

    def read_string() -> str:
        nonlocal i
        start = i
        while i < size and payload[i] not in _MSDP_DELIMITERS:
            i += 1
        return payload[start:i].decode(encoding, errors="replace")

    def fail(reason: str) -> OobDecodeError:
        return OobDecodeError(f"MSDP {reason}", name=last_name)

    while i < size or len(stack) > 1:
        if i >= size:
            raise fail("payload ends inside a table or array")
        frame = stack[-1]
        container = frame.container
        byte = payload[i]
        i += 1

        if isinstance(container, dict):
            if byte == _MSDP_TABLE_CLOSE and len(stack) > 1:
                stack.pop()
                continue
            if byte != _MSDP_VAR:
                raise fail("expected a variable")
            key = read_string()
            if len(stack) == 1:
                if not valid_variable(key):
                    raise fail("variable name is not valid")
                last_name = key
            elif not key:
                raise fail("table key is empty")
            if i >= size or payload[i] != _MSDP_VAL:
                raise fail("variable has no value")
            i += 1
            frame.key = key
        else:
            if byte == _MSDP_ARRAY_CLOSE:
                stack.pop()
                continue
            if byte != _MSDP_VAL:
                raise fail("expected an array item")

        # the value: a table, an array or a string
        nodes += 1
        if nodes > MSDP_MAX_NODES:
            raise fail("has too many values")
        value: dict[str, Any] | list[Any] | str
        if i < size and payload[i] == _MSDP_TABLE_OPEN:
            i += 1
            value = {}
            stack_push: _MsdpFrame | None = _MsdpFrame(value)
        elif i < size and payload[i] == _MSDP_ARRAY_OPEN:
            i += 1
            value = []
            stack_push = _MsdpFrame(value)
        else:
            value = read_string()
            stack_push = None
        if isinstance(container, dict):
            assert frame.key is not None
            container[frame.key] = value
        else:
            container.append(value)
        if stack_push is not None:
            if len(stack) > MSDP_MAX_DEPTH:
                raise fail("nests too deep")
            stack.append(stack_push)

    if not top:
        raise fail("payload has no variables")
    return top


def decode_mssp(payload: bytes, encoding: str = "utf-8") -> dict[str, str | list[str]]:
    """Decode an MSSP payload into a dict of variable name to a ``str`` or a ``list[str]``.

    The payload is checked against ``OOB_MAX_PAYLOAD`` first, decoded with telnetlib3, then
    filtered: a variable whose name is not valid is skipped; variables past
    ``MSSP_MAX_VARIABLES`` are skipped; a variable keeps at most ``MSSP_MAX_VALUES`` values;
    a value longer than ``MSSP_MAX_VALUE_LEN`` characters is skipped. One DEBUG line per call
    says what was skipped.

    Raises:
        OobDecodeError: If the payload is over ``OOB_MAX_PAYLOAD``, or no valid variable is
            left after filtering.

    """
    if len(payload) > OOB_MAX_PAYLOAD:
        msg = "MSSP payload over the size limit"
        raise OobDecodeError(msg)
    raw = mssp_decode(payload, encoding)
    result: dict[str, str | list[str]] = {}
    bad_names = over_variables = over_values = long_values = 0
    for name, value in raw.items():
        if not valid_mssp_name(name):
            bad_names += 1
            continue
        if len(result) >= MSSP_MAX_VARIABLES:
            over_variables += 1
            continue
        values = value if isinstance(value, list) else [value]
        if len(values) > MSSP_MAX_VALUES:
            over_values += len(values) - MSSP_MAX_VALUES
            values = values[:MSSP_MAX_VALUES]
        kept = [item for item in values if len(item) <= MSSP_MAX_VALUE_LEN]
        long_values += len(values) - len(kept)
        if not kept:
            continue
        result[name] = kept if isinstance(value, list) and len(kept) > 1 else kept[0]
    if bad_names or over_variables or over_values or long_values:
        logger.debug(
            "MSSP skipped: %d invalid names, %d variables past the limit, %d values past "
            "the limit, %d values over the length limit",
            bad_names,
            over_variables,
            over_values,
            long_values,
        )
    if not result:
        msg = "MSSP payload has no valid variables"
        raise OobDecodeError(msg)
    return result


def merge_gmcp(old: Any, new: Any) -> Any:
    """Return the cached value after a GMCP update.

    Two dicts are shallow-merged. When the merged value would encode larger than
    ``OOB_MAX_PAYLOAD``, or either value is not a dict, ``new`` replaces ``old``.
    """
    if isinstance(old, dict) and isinstance(new, dict):
        merged = {**old, **new}
        try:
            if len(json.dumps(merged)) <= OOB_MAX_PAYLOAD:
                return merged
        except (TypeError, ValueError):
            pass
    return new


def parse_supports(items: Any) -> dict[str, int]:
    """Parse the data of a ``Core.Supports.*`` message or a module list.

    ``items`` is a list of strings such as ``"Char 1"``; a missing version means 1. Entries
    that do not match are skipped, and at most ``CLIENT_MAX_MODULES`` valid entries are kept.
    The result maps the lower-cased module name to the highest version listed for it.
    """
    modules: dict[str, int] = {}
    if not isinstance(items, list):
        return modules
    for item in items:
        if not isinstance(item, str):
            continue
        match = _MODULE_RE.fullmatch(item)
        if match is None:
            continue
        name = match.group(1).lower()
        version = int(match.group(2)) if match.group(2) is not None else 1
        if name not in modules and len(modules) >= CLIENT_MAX_MODULES:
            continue
        modules[name] = max(version, modules.get(name, 0))
    return modules


def supports_payload(modules: dict[str, int]) -> list[str]:
    """Format a module dict as the sorted list ``Core.Supports.Set`` carries."""
    return [f"{name} {modules[name]}" for name in sorted(modules)]


def package_wanted(package: str, modules: Iterable[str]) -> bool:
    """Whether ``package`` belongs to one of ``modules``.

    A package matches module ``m`` when ``package.lower() == m`` or it starts with ``m + "."``,
    so ``Char`` matches ``Char.Vitals`` but not ``Character.X``.
    """
    lowered = package.lower()
    return any(lowered == m or lowered.startswith(f"{m}.") for m in modules)


def is_credential_package(package: str) -> bool:
    """Whether ``package`` carries login data: ``Char.Login`` or a package under it.

    Records and logs keep the name of such a message but never its data.
    """
    lowered = package.lower()
    return lowered == "char.login" or lowered.startswith("char.login.")


def redact_gmcp_payload(payload: bytes) -> bytes:
    """Return ``payload`` unchanged, or with its body replaced when it is login data.

    The payload is ``Package.Name`` optionally followed by a space and JSON; for a package
    that ``is_credential_package`` names, the JSON becomes ``REDACTED``.
    """
    package = payload.split(b" ", 1)[0].decode("ascii", errors="replace")
    if is_credential_package(package):
        return f"{package} {REDACTED}".encode("ascii", errors="replace")
    return payload
