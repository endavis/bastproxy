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
    - `go_ahead`: Return the Telnet opcode for "Go Ahead".
    - `end_of_record`: Return the Telnet opcode for "End of Record".

"""

from telnetlib3.telopt import CMD_EOR, GA, IAC


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


def end_of_record() -> bytes:
    """Return the Telnet command for IAC EOR.

    The command byte ``CMD_EOR`` (0xEF) follows ``IAC``, not the option byte ``EOR`` (25).

    Returns:
        The Telnet command sequence marking the end of a prompt record.

    """
    return IAC + CMD_EOR
