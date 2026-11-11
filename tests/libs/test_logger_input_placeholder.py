"""Tests for the log placeholder builder."""

from bastproxy.libs.logger import input_placeholder


def test_default_context() -> None:
    assert input_placeholder("abcd\r\n") == "<input before login, 6 chars>"


def test_empty_line() -> None:
    assert input_placeholder("") == "<input before login, 0 chars>"


def test_custom_context_hides_line() -> None:
    result = input_placeholder("hello", "input while echo is off")
    assert result == "<input while echo is off, 5 chars>"
    assert "hello" not in result


def test_echo_off_placeholder_strips_the_line_ending() -> None:
    from bastproxy.libs.logger import echo_off_placeholder

    assert echo_off_placeholder("abcd\r\n") == "<input while echo is off, 4 chars>"
    assert echo_off_placeholder(b"abcd") == "<input while echo is off, 4 chars>"
