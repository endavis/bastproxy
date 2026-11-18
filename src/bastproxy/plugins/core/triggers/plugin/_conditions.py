# Project: bastproxy
# Filename: plugins/core/triggers/plugin/_conditions.py
#
# File Description: parse and evaluate the GMCP conditions (``when=``) of a trigger
#
# By: Bast
"""GMCP conditions for triggers.

A ``when`` mapping is ``{"Char.Vitals.hp": ">50"}``: a dotted GMCP path and a
comparison string. It is parsed once, when the trigger is added or updated, and
evaluated against the decoded GMCP cache through a lookup callable. The path resolver is
``resolve_gmcp_path`` in ``libs/net/oob.py``, shared with ``gmcp.value.get``.
"""

# Standard Library
import dataclasses
import math
from collections.abc import Callable, Mapping
from typing import Any

# First Party
from bastproxy.libs.net.oob import MISSING as _MISSING
from bastproxy.libs.net.oob import resolve_gmcp_path as resolve

# Longest first, so ">=" is not read as ">" followed by "=50"
_OPERATORS = (">=", "<=", "!=", ">", "<", "=")
_ORDERING = frozenset({">", ">=", "<", "<="})


@dataclasses.dataclass(frozen=True, slots=True)
class Condition:
    """One parsed condition: ``path`` compared to ``operand`` with ``operator``."""

    path: str
    operator: str
    operand: str
    number: float | None


def _to_number(value: Any) -> float | None:
    """The finite number a value stands for, or None (booleans are not numbers)."""
    if isinstance(value, bool):
        return None
    if isinstance(value, int | float):
        number = float(value)
    elif isinstance(value, str):
        try:
            number = float(value)
        except ValueError:
            return None
    else:
        return None
    return number if math.isfinite(number) else None


def _as_text(value: Any) -> str:
    """The text a value is compared as for ``=`` and ``!=``."""
    if isinstance(value, bool):
        return "true" if value else "false"
    return str(value)


def _parse_one(path: Any, spec: Any) -> Condition:
    """Parse one path and comparison string, raising ValueError when invalid."""
    if not isinstance(path, str) or not isinstance(spec, str):
        raise ValueError(f"when: path and condition must be strings, got {path!r}: {spec!r}")
    if not path or any(not segment for segment in path.split(".")):
        raise ValueError(f"when: invalid GMCP path {path!r}")
    text = spec.strip()
    operator = next((op for op in _OPERATORS if text.startswith(op)), None)
    if operator is None:
        raise ValueError(f"when: {path!r}: condition {spec!r} does not start with an operator")
    operand = text[len(operator) :].strip()
    if not operand:
        raise ValueError(f"when: {path!r}: condition {spec!r} has no operand")
    number = _to_number(operand)
    if operator in _ORDERING and number is None:
        raise ValueError(
            f"when: {path!r}: operator {operator} needs a finite number, got {operand!r}"
        )
    return Condition(path, operator, operand, number)


def parse_conditions(when: Any) -> tuple[Condition, ...]:
    """Parse a ``when`` mapping; ``None`` or an empty mapping gives no conditions."""
    if when is None:
        return ()
    if not isinstance(when, Mapping):
        raise ValueError(
            f"when must be a dict of GMCP path to condition, got {type(when).__name__}"
        )
    return tuple(_parse_one(path, spec) for path, spec in when.items())


def _holds(condition: Condition, value: Any) -> bool:
    """Whether one resolved value satisfies a condition."""
    operator = condition.operator
    number = _to_number(value)
    if operator in _ORDERING:
        if number is None or condition.number is None:
            return False
        if operator == ">":
            return number > condition.number
        if operator == ">=":
            return number >= condition.number
        if operator == "<":
            return number < condition.number
        return number <= condition.number
    if number is not None and condition.number is not None:
        equal = number == condition.number
    else:
        equal = _as_text(value) == condition.operand
    return equal if operator == "=" else not equal


def check(conditions: tuple[Condition, ...], lookup: Callable[[str], Any]) -> bool:
    """True when every condition holds; a missing value fails every condition."""
    for condition in conditions:
        value = resolve(condition.path, lookup)
        if value is _MISSING or not _holds(condition, value):
            return False
    return True
