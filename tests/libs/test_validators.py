"""Tests for bastproxy.libs.validators and its re-export from the settings plugin (#611)."""

from bastproxy.libs import validators
from bastproxy.plugins.core import settings as settings_plugin


def test_int_range() -> None:
    check = validators.int_range(minimum=1, maximum=10)
    assert check(5) == ""
    assert check(0)
    assert check(11)


def test_non_empty() -> None:
    check = validators.non_empty()
    assert check("x") == ""
    assert check("")


def test_validate_port() -> None:
    assert validators.validate_port(80) == ""
    assert validators.validate_port(0)
    assert validators.validate_port(70000)


def test_validate_port_or_unset() -> None:
    assert validators.validate_port_or_unset(0) == ""
    assert validators.validate_port_or_unset(8080) == ""
    assert validators.validate_port_or_unset(70000)


def test_validate_hosts() -> None:
    assert validators.validate_ipv4_host("127.0.0.1") == ""
    assert validators.validate_ipv4_host("::1")
    assert validators.validate_ipv6_host("::1") == ""
    assert validators.validate_ipv6_host("1.2.3.4")


def test_settings_plugin_reexports_same_objects() -> None:
    for name in (
        "int_range",
        "non_empty",
        "validate_ipv4_host",
        "validate_ipv6_host",
        "validate_port",
        "validate_port_or_unset",
    ):
        assert getattr(settings_plugin, name) is getattr(validators, name)
