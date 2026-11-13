# Project: bastproxy
# Filename: plugins/core/settings/libs/_validators.py
#
# File Description: shared validators for setting values
#
# By: Bast
"""Validators for ``setting.add(..., validator=...)``.

A validator takes the converted value and returns "" when it is valid, else an error message.
"""

# Standard Library
import ipaddress
import re
from collections.abc import Callable
from typing import Any

MAX_PORT = 65535
MAX_HOSTNAME_LENGTH = 253
_LABEL = re.compile(r"^[A-Za-z0-9]([A-Za-z0-9-]{0,61}[A-Za-z0-9])?$")
_DIGITS_AND_DOTS = re.compile(r"^[0-9.]+$")


def int_range(
    minimum: int, maximum: int | None = None, *, label: str = "value"
) -> Callable[[Any], str]:
    """Build a validator for an int of at least ``minimum`` (and at most ``maximum``)."""

    def validator(value: Any) -> str:
        if isinstance(value, bool) or not isinstance(value, int):
            return f"the {label} must be a whole number"
        if value < minimum or (maximum is not None and value > maximum):
            if maximum is None:
                return f"the {label} must be at least {minimum}"
            return f"the {label} must be between {minimum} and {maximum}"
        return ""

    return validator


def non_empty(*, label: str = "value") -> Callable[[Any], str]:
    """Build a validator that refuses an empty string or a non-str value."""

    def validator(value: Any) -> str:
        if not isinstance(value, str) or not value:
            return f"the {label} cannot be empty"
        return ""

    return validator


validate_port = int_range(1, MAX_PORT, label="port")


def validate_port_or_unset(value: Any) -> str:
    """Validate a port, where 0 means "unset"."""
    if value == 0 and not isinstance(value, bool):
        return ""
    return "the port must be 0 (unset) or between 1 and 65535" if validate_port(value) else ""


def _hostname_error(value: str) -> str:
    if not value or len(value) > MAX_HOSTNAME_LENGTH:
        return "the host must be an IP address or a hostname of 1 to 253 characters"
    if _DIGITS_AND_DOTS.match(value):
        return "the host looks like an IPv4 address but is not a valid one"
    if not all(_LABEL.match(label) for label in value.rstrip(".").split(".")):
        return "the host is not a valid IP address or hostname"
    return ""


def _validate_host(value: Any, version: int) -> str:
    if not isinstance(value, str):
        return "the host must be text"
    try:
        address = ipaddress.ip_address(value)
    except ValueError:
        return _hostname_error(value)
    if address.version != version:
        return f"the host must be an IPv{version} address or a hostname"
    return ""


def validate_ipv4_host(value: Any) -> str:
    """Validate an IPv4 literal or a hostname."""
    return _validate_host(value, 4)


def validate_ipv6_host(value: Any) -> str:
    """Validate an IPv6 literal or a hostname."""
    return _validate_host(value, 6)
