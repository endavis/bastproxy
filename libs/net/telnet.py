# Project: bastproxy
# Filename: libs/net/telnet.py
#
# File Description: Consolidate various protocols.
#
# By: Bast/Jubelo
"""Module for handling Telnet protocol operations and commands.

This module provides functions and constants for working with the Telnet protocol,
including building commands, handling sub-negotiations, and managing opcodes. It
includes utility functions for constructing Telnet commands, advertising features,
and handling opcodes received from a connected client.

Key Components:
    - Constants for Telnet protocol opcodes.
    - Utility functions for building and handling Telnet commands.
    - Functions for advertising features and managing Telnet options.

Features:
    - Construction of Telnet commands and sub-negotiation commands.
    - Handling and decoding of received Telnet opcodes.
    - Advertising game capabilities to connected clients.
    - Enabling and disabling Telnet echo mode.

Usage:
    - Use `iac` and `iac_sb` to build Telnet commands.
    - Use `split_opcode_from_input` to separate opcodes from input data.
    - Use `advertise_features` to build a byte string of features to advertise.
    - Use `handle` to decode and handle received Telnet opcodes.

Functions:
    - `iac`: Build Telnet commands on the fly.
    - `iac_sb`: Build Telnet sub-negotiation commands on the fly.
    - `split_opcode_from_input`: Separate opcodes from input data.
    - `advertise_features`: Build and return a byte string of features to advertise.
    - `echo_on`: Return the Telnet opcode for enabling echo.
    - `echo_off`: Return the Telnet opcode for disabling echo.
    - `go_ahead`: Return the Telnet opcode for "Go Ahead".
    - `handle`: Decode and handle received Telnet opcodes.

"""

# Standard Library
import logging
from string import printable
from typing import TYPE_CHECKING

# Third Party

if TYPE_CHECKING:
    from telnetlib3 import TelnetWriterUnicode

# Basic Telnet protocol opcodes. The MSSP character will be imported from it's module.
IAC: bytes = bytes([255])  # "Interpret As Command"
DONT: bytes = bytes([254])
DO: bytes = bytes([253])
WONT: bytes = bytes([252])
WILL: bytes = bytes([251])
SB: bytes = bytes([250])  # Subnegotiation Begin
GA: bytes = bytes([249])  # Go Ahead
SE: bytes = bytes([240])  # Subnegotiation End
CHARSET: bytes = bytes([42])  # CHARSET
NAWS: bytes = bytes([31])  # window size
EOR: bytes = bytes([25])  # end or record
TTYPE: bytes = bytes([24])  # terminal type
ECHO: bytes = bytes([1])  # echo
theNULL: bytes = bytes([0])

# Telnet protocol by string designators
code: dict[str, bytes] = {
    "IAC": bytes([255]),
    "DONT": bytes([254]),
    "DO": bytes([253]),
    "WONT": bytes([252]),
    "WILL": bytes([251]),
    "SB": bytes([250]),
    "GA": bytes([249]),
    "SE": bytes([240]),
    "MSSP": bytes([70]),
    "CHARSET": bytes([42]),
    "NAWS": bytes([31]),
    "EOR": bytes([25]),
    "TTYPE": bytes([24]),
    "ECHO": bytes([1]),
    "theNull": bytes([0]),
}

# Telnet protocol, int representation as key, string designator value.
code_by_byte: dict[int, str] = {ord(v): k for k, v in code.items()}

# Game capabilities to advertise
GAME_CAPABILITIES: list[str] = []


# Utility functions
def iac(codes: list) -> bytes:
    """Build Telnet commands on the fly.

    This function constructs a Telnet command from a list of codes. Each code can be
    a string, an integer, or bytes. The resulting command is prefixed with the IAC
    (Interpret As Command) byte.

    Args:
        codes: A list of codes to include in the Telnet command.

    Returns:
        The constructed Telnet command as a byte string.

    Raises:
        None

    """
    command = []

    for each_code in codes:
        if isinstance(each_code, str):
            command.append(each_code.encode())
        elif isinstance(each_code, int):
            command.append(str(each_code).encode())
        else:
            command.append(each_code)

    command = b"".join(command)

    return IAC + command


def iac_sb(codes: list) -> bytes:
    """Build Telnet sub-negotiation commands on the fly.

    This function constructs a Telnet sub-negotiation command from a list of codes.
    Each code can be a string, an integer, or bytes. The resulting command is prefixed
    with the IAC (Interpret As Command) and SB (Subnegotiation Begin) bytes, and
    suffixed with the IAC and SE (Subnegotiation End) bytes.

    Args:
        codes: A list of codes to include in the Telnet sub-negotiation command.

    Returns:
        The constructed Telnet sub-negotiation command as a byte string.

    Raises:
        None

    """
    command = []

    for each_code in codes:
        if isinstance(each_code, str):
            command.append(each_code.encode())
        elif isinstance(each_code, int):
            command.append(str(each_code).encode())
        else:
            command.append(each_code)

    command = b"".join(command)

    return IAC + SB + command + IAC + SE


def split_opcode_from_input(data: bytes) -> tuple[bytes, str]:
    """Separate opcodes from input data.

    This function processes the input data to separate Telnet opcodes from printable
    characters. It returns a tuple containing the opcodes as a byte string and the
    remaining input as a string.

    Args:
        data: The input data as a byte string.

    Returns:
        A tuple containing the opcodes as a byte string and the remaining input as a
        string.

    Raises:
        None

    """
    logging.getLogger(__name__).debug("Received raw data (len=%d of: %s", len(data), data)
    opcodes = b""
    inp = ""
    for position, _ in enumerate(data):
        if data[position] in code_by_byte:
            opcodes += bytes([data[position]])
        elif chr(data[position]) in printable:
            inp += chr(data[position])
    logging.getLogger(__name__).debug(
        "Bytecodes found in input.\n\ropcodes: %s\n\rinput returned: %s", opcodes, inp
    )
    return opcodes, inp


def advertise_features() -> bytes:
    """Build and return a byte string of features to advertise.

    This function constructs a byte string of game capabilities to advertise to the
    connected client. Each capability is prefixed with the IAC (Interpret As Command)
    and WILL bytes.

    Args:
        None

    Returns:
        The constructed byte string of features to advertise.

    Raises:
        None

    """
    features = b""
    for each_feature in GAME_CAPABILITIES:
        features += features + IAC + WILL + code[each_feature]
    logging.getLogger(__name__).debug("Advertising features: %s", features)
    return features


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


# Define a dictionary of responses to various received opcodes.
opcode_match: dict = {}

# Future.
main_negotiations: tuple = (WILL, WONT, DO, DONT)


# Primary function for decoding and handling received opcodes.
async def handle(opcodes: bytes, writer: "TelnetWriterUnicode") -> None:
    """Decode and handle received Telnet opcodes.

    This function processes the received Telnet opcodes and handles them according
    to predefined responses. It splits the opcodes by the IAC (Interpret As Command)
    byte and matches each opcode to a corresponding response. The response is then
    written to the Telnet writer.

    Args:
        opcodes: The received Telnet opcodes as a byte string.
        writer: The Telnet writer to send responses to.

    Returns:
        None

    Raises:
        None

    """
    logging.getLogger(__name__).debug("Handling opcodes: %s", opcodes)
    for each_code in opcodes.split(IAC):
        if each_code and each_code in opcode_match:
            result = iac_sb(opcode_match[each_code]())
            logging.getLogger(__name__).debug(
                "Responding to previous opcode with: %s", result
            )
            writer.write(result)
            await writer.drain()
    logging.getLogger(__name__).debug("Finished handling opcodes.")
