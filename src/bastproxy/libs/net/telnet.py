# Project: bastproxy
# Filename: libs/net/telnet.py
#
# File Description: Raw Telnet opcodes bastproxy sends itself.
#
# By: Bast/Jubelo
"""Module for building Telnet protocol opcodes.

This module provides the few raw Telnet byte sequences bastproxy sends itself. The
opcode constants come from `telnetlib3.telopt`.

Functions:
    - `echo_on`: Return the Telnet opcode for enabling echo.
    - `echo_off`: Return the Telnet opcode for disabling echo.
    - `go_ahead`: Return the Telnet opcode for "Go Ahead".

"""

from telnetlib3.telopt import ECHO, GA, IAC, WILL, WONT


def echo_on() -> bytes:
    """Return the Telnet opcode for IAC WILL ECHO.

    This function constructs and returns the Telnet opcode sequence for enabling
    echo mode. The sequence is prefixed with the IAC (Interpret As Command) byte
    and the WILL byte, followed by the ECHO byte.

    Args:
        None

    Returns:
        The Telnet opcode sequence for enabling echo mode.

    Raises:
        None

    """
    return IAC + WILL + ECHO


def echo_off() -> bytes:
    """Return the Telnet opcode for IAC WONT ECHO.

    This function constructs and returns the Telnet opcode sequence for disabling
    echo mode. The sequence is prefixed with the IAC (Interpret As Command) byte
    and the WONT byte, followed by the ECHO byte.

    Args:
        None

    Returns:
        The Telnet opcode sequence for disabling echo mode.

    Raises:
        None

    """
    return IAC + WONT + ECHO


def go_ahead() -> bytes:
    """Return the Telnet opcode for IAC GA.

    This function constructs and returns the Telnet opcode sequence for the "Go Ahead"
    command. The sequence is prefixed with the IAC (Interpret As Command) byte and
    followed by the GA byte.

    Args:
        None

    Returns:
        The Telnet opcode sequence for the "Go Ahead" command.

    Raises:
        None

    """
    return IAC + GA
