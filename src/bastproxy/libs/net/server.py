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
import zlib
from collections.abc import Coroutine
from typing import Any

# 3rd Party
import telnetlib3
from telnetlib3.telopt import (
    BINARY,
    DO,
    EOR,
    GMCP,
    IAC,
    MCCP2_COMPRESS,
    MCCP3_COMPRESS,
    MSDP,
    MSSP,
    MXP,
    NAWS,
    SE,
    WILL,
)

# Project
from bastproxy.libs.logger import get_logger
from bastproxy.libs.net.inflate import BoundedDecompressor
from bastproxy.libs.net.negotiation import RecordingTelnetWriter

logger = get_logger(__name__)

#: Most bytes one received chunk of a client's MCCP3 stream may inflate to. An asyncio socket
#: read is at most 256 KiB, so 16 MiB allows 64 to 1 on a full read; the same limit as the MUD
#: side (``MCCP2_MAX_INFLATED_CHUNK``, #58).
MCCP3_MAX_INFLATED_CHUNK = 16 * 1024 * 1024

_IAC_SE = IAC + SE


class CustomTelnetServer(telnetlib3.TelnetServer):
    """Represents a custom Telnet server with advanced negotiation.

    This class extends the `telnetlib3.TelnetServer` class to provide a custom Telnet
    server with advanced negotiation capabilities.

    """

    # class default for tests that build the protocol without __init__
    _mccp2_enabled: bool = False
    _mccp3_inflater: BoundedDecompressor | None = None
    mccp3_failed: bool = False

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

        Sent when the listener passes ``compression=True`` and the link is not TLS
        (the guard telnetlib3 uses): ``WILL MCCP2_COMPRESS`` and ``WILL MCCP3_COMPRESS``.
        MCCP2 starts when the client answers ``DO``. MCCP3 is accepted only after this offer
        (``always_will``); a client that agrees then sends ``SB MCCP3`` and compresses its
        stream, which ``data_received`` inflates with a bound (#329).

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
            self.writer.always_will.add(MCCP3_COMPRESS)
            self.writer.iac(WILL, MCCP3_COMPRESS)

    def _mccp3_start(self) -> None:
        """Do nothing: telnetlib3's MCCP3 inflater is never used; ``data_received`` has its own."""
        logger.debug("telnetlib3 MCCP3 start ignored on a client link")

    def _mccp3_fail(self) -> None:
        """Close this client's link after a broken or over-limit MCCP3 stream (#329)."""
        self.mccp3_failed = True
        self._mccp3_inflater = None
        logger.error(
            "MCCP3 decompression error on a client link (a broken stream or a chunk over the "
            "inflation limit), closing the connection to the client"
        )
        self.writer.close()

    def _feed_telnet(self, data: bytes) -> None:
        """Hand plain telnet bytes to telnetlib3, ending MCCP2 when the client turned it off.

        telnetlib3 5.0.2 starts compression on ``DO MCCP2`` but keeps compressing after
        a later ``DONT MCCP2``. End the stream (``Z_FINISH``) so the rest is plain, and
        a later ``DO`` starts a new stream (#58).
        """
        super().data_received(data)
        if self._mccp2_compressor is not None and not self.writer.local_option.enabled(
            MCCP2_COMPRESS
        ):
            self._mccp2_end()

    def _feed_pieces(self, data: bytes) -> bytes:
        """Feed plain telnet bytes piece by piece, stopping where an MCCP3 stream starts.

        Pieces end after each ``IAC SE`` (and after a leading ``SE``, for an ``IAC`` and
        ``SE`` split across reads), so a parsed ``SB MCCP3`` is seen before the bytes behind
        it are read. Splitting is safe: telnetlib3 parses byte by byte. Returns the bytes
        after a started stream, which are compressed; otherwise ``b""``. A start requested
        while a stream is already open is cleared.
        """
        while data and not self.mccp3_failed:
            if data[:1] == SE:
                end = 1
            else:
                found = data.find(_IAC_SE)
                end = len(data) if found == -1 else found + 2
            piece, data = data[:end], data[end:]
            self._feed_telnet(piece)
            if not self.writer.mccp3_start_requested:
                continue
            self.writer.mccp3_start_requested = False
            if self._mccp3_inflater is not None:
                logger.debug("Ignored an SB MCCP3 inside an open MCCP3 stream")
                continue
            self._mccp3_inflater = BoundedDecompressor(
                zlib.decompressobj(), MCCP3_MAX_INFLATED_CHUNK
            )
            return data
        return b""

    def _feed_compressed(self, data: bytes) -> bytes:
        """Inflate bounded *data* of an open stream and feed it on; return bytes after its end."""
        inflater = self._mccp3_inflater
        if inflater is None:
            return data
        try:
            out = inflater.decompress(data)
        except zlib.error:
            self._mccp3_fail()
            return b""
        rest = b""
        ended = bool(inflater.eof)
        if ended:
            rest = bytes(inflater.unused_data)
        self._feed_pieces(out)
        if ended:
            self._mccp3_inflater = None
        return rest

    def data_received(self, data: bytes) -> None:
        """Process client data, inflating a client's MCCP3 stream when it was agreed (#329).

        MCCP3 starts only when the proxy offered it and the client agreed (see
        ``RecordingTelnetWriter._handle_sb_mccp3``); the stream can start mid-chunk. Every
        inflate is bounded by ``MCCP3_MAX_INFLATED_CHUNK``. A broken stream or one over the
        bound closes this client's link, and nothing more from it is processed. After a
        clean end the rest of the data is plain again.
        """
        while data and not self.mccp3_failed:
            if self._mccp3_inflater is None:
                data = self._feed_pieces(data)
            else:
                data = self._feed_compressed(data)


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
