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
import sys
from collections.abc import Coroutine

# 3rd Party
try:
    import telnetlib3
except ImportError:
    print("Please install required libraries. telnetlib3 is missing.")
    print("From the root of the project: pip(3) install -r requirements.txt")
    sys.exit(1)

# Project


class CustomTelnetServer(telnetlib3.TelnetServer):
    """Represents a custom Telnet server with advanced negotiation.

    This class extends the `telnetlib3.TelnetServer` class to provide a custom Telnet
    server with advanced negotiation capabilities.

    """

    def begin_advanced_negotiation(self) -> None:
        """Begin advanced negotiation with the client.

        This method initiates advanced negotiation with the client to set up the
        communication parameters and options.

        Returns:
            None

        Raises:
            NotImplementedError: If the method is not implemented.

        """

        # if self.writer and self.default_encoding:
        #     self.writer.iac(DO, CHARSET)


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
