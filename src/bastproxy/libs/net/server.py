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
from typing import Any

# 3rd Party
import telnetlib3
from telnetlib3.telopt import BINARY, DO, EOR, GMCP, MCCP2_COMPRESS, MSDP, MSSP, MXP, NAWS, WILL

# Project
from bastproxy.libs.net.negotiation import RecordingTelnetWriter


class CustomTelnetServer(telnetlib3.TelnetServer):
    """Represents a custom Telnet server with advanced negotiation.

    This class extends the `telnetlib3.TelnetServer` class to provide a custom Telnet
    server with advanced negotiation capabilities.

    """

    # class default for tests that build the protocol without __init__
    _mccp2_enabled: bool = False

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        """Initialize the server, defaulting to the writer that records negotiation (#83)."""
        kwargs.setdefault("writer_factory_encoding", RecordingTelnetWriter)
        super().__init__(*args, **kwargs)

    def begin_advanced_negotiation(self) -> None:
        """Begin advanced negotiation with a newly connected client.

        Replaces telnetlib3's implementation and does not call it. Sent here:

        - ``DO NAWS``, so the client reports its window size (telnetlib3 stores
          it as the ``rows`` and ``cols`` extra info, see ``ClientConnection``).
        - ``WILL BINARY``, so the proxy may send 8-bit data (utf8) to the client.
        - ``WILL MXP``, so a client can take the MUD's MXP markup; a client without MXP gets the
          text with the markup stripped (#61).
        - ``WILL EOR``, so a client that agrees gets ``IAC EOR`` after each prompt instead of
          ``IAC GA``; a client that refuses still gets ``IAC GA`` unless it agreed to SGA (#272).
        - ``WILL GMCP``, ``WILL MSDP`` and ``WILL MSSP``, so a client can take the MUD's
          out-of-band data and status table from the proxy, which terminates these protocols on
          every link (ADR-0001, #59, #60). A client receives nothing until it answers ``DO``
          and has logged in.

        Deliberately not sent:

        - ``WILL SGA``: with SGA enabled ``send_ga()`` sends no GA, and MUD
          clients use GA to find prompts. A client may still send ``DO SGA`` on its own, which
          telnetlib3 accepts and which then suppresses GA (#272).
        - ``DO CHARSET``: ``force_binary=True`` on the listeners already fixes
          the encoding (#63) and CHARSET could renegotiate it.
        - ``WILL MCCP3``: telnetlib3 5.0.2 cannot serve client-side MCCP3 (it answers
          ``DO MCCP3`` with ``WONT``), so only MCCP2 is offered (#58, #329).

        Sent when the listener passes ``compression=True`` and the link is not TLS
        (the guard telnetlib3 uses): ``WILL MCCP2_COMPRESS``. Compression starts when
        the client answers ``DO``.

        telnetlib3 still sends ``DO NEW_ENVIRON`` and its own deferred
        ``WILL ECHO`` from its own code, outside this method.

        """
        self.writer.iac(DO, NAWS)
        self.writer.iac(WILL, BINARY)
        self.writer.iac(WILL, GMCP)
        self.writer.iac(WILL, MSDP)
        self.writer.iac(WILL, MSSP)
        self.writer.iac(WILL, MXP)
        self.writer.iac(WILL, EOR)
        if self._mccp2_enabled and self.writer.get_extra_info("ssl_object") is None:
            self.writer.iac(WILL, MCCP2_COMPRESS)

    def data_received(self, data: bytes) -> None:
        """Process client data, ending MCCP2 when the client turns it off.

        telnetlib3 5.0.2 starts compression on ``DO MCCP2`` but keeps compressing after
        a later ``DONT MCCP2``. End the stream (``Z_FINISH``) so the rest is plain, and
        a later ``DO`` starts a new stream (#58).
        """
        super().data_received(data)
        if self._mccp2_compressor is not None and not self.writer.local_option.enabled(
            MCCP2_COMPRESS
        ):
            self._mccp2_end()


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
