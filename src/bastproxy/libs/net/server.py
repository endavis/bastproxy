# Project: bastproxy
# Filename: libs/net/server.py
#
# File Description: creates the server for the proxy
#
# By: Bast
"""Module for creating a custom Telnet server for the proxy.

This module provides the `CustomTelnetServer` class, which extends the `TelnetServer`
class from the `telnetlib3` library to create a custom Telnet server. It includes a
method for advanced negotiation and a factory function for creating the server.

Key Components:
    - CustomTelnetServer: A class that extends `telnetlib3.TelnetServer`.
    - create_server: A factory function for creating the custom Telnet server.

Features:
    - CustomTelnetServer class with a method for advanced negotiation.
    - Factory function to create the server with the custom protocol.

Usage:
    - Instantiate the server using the `create_server` function with the desired
        arguments and keyword arguments.

Classes:
    - `CustomTelnetServer`: Represents a custom Telnet server with advanced negotiation.

Functions:
    - `create_server`: Creates the custom Telnet server with the specified protocol.
"""

# Standard Library
from collections.abc import Coroutine

# 3rd Party
import telnetlib3
from telnetlib3.telopt import BINARY, DO, NAWS, WILL

# Project


class CustomTelnetServer(telnetlib3.TelnetServer):
    """Represents a custom Telnet server with advanced negotiation.

    This class extends the `telnetlib3.TelnetServer` class to provide a custom Telnet
    server with advanced negotiation capabilities.

    """

    def begin_advanced_negotiation(self) -> None:
        """Begin advanced negotiation with a newly connected client.

        Replaces telnetlib3's implementation and does not call it. Sent here:

        - ``DO NAWS``, so the client reports its window size (telnetlib3 stores
          it as the ``rows`` and ``cols`` extra info, see ``ClientConnection``).
        - ``WILL BINARY``, so the proxy may send 8-bit data (utf8) to the client.

        Deliberately not sent:

        - ``WILL SGA``: with SGA enabled ``send_ga()`` sends no GA, and MUD
          clients use GA to find prompts (#272 depends on it).
        - ``DO CHARSET``: ``force_binary=True`` on the listeners already fixes
          the encoding (#63) and CHARSET could renegotiate it.
        - MCCP: the listeners pass ``compression=False``.

        telnetlib3 still sends ``DO NEW_ENVIRON`` and its own deferred
        ``WILL ECHO`` from its own code, outside this method.

        """
        self.writer.iac(DO, NAWS)
        self.writer.iac(WILL, BINARY)


def create_server(*args, **kwargs) -> Coroutine:
    """Create the custom Telnet server with the specified protocol.

    This factory function creates a custom Telnet server using the `CustomTelnetServer`
    class as the protocol factory. It accepts any arguments and keyword arguments
    supported by the `telnetlib3.create_server` function.

    Args:
        *args: Positional arguments to be passed to `telnetlib3.create_server`.
        **kwargs: Keyword arguments to be passed to `telnetlib3.create_server`.

    Returns:
        A coroutine that creates the custom Telnet server.

    Raises:
        Any exception raised by `telnetlib3.create_server`.

    """
    kwargs["protocol_factory"] = CustomTelnetServer
    return telnetlib3.create_server(*args, **kwargs)
