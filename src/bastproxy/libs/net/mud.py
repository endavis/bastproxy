# Project: bastproxy
# Filename: libs/net/mud.py
#
# File Description: MUD connection handling.
#
# By: Bast/Jubelo
"""Module for handling client connections to a MUD server.

This module provides the `MudConnection` class, which manages the connection
to a MUD server, including reading from and writing to the server, handling
telnet options, and managing the connection state.

Key Components:
    - MudConnection: A class that manages the connection to a MUD server.
    - Methods for connecting, disconnecting, reading, and writing to the MUD server.
    - Utility methods for handling telnet options and managing the connection state.

Features:
    - Asynchronous connection handling using asyncio.
    - Telnet option negotiation and handling.
    - Queue-based message sending to the MUD server.
    - Comprehensive logging of connection events and data transmission.

Usage:
    - Instantiate MudConnection with the server address and port.
    - Use `connect_to_mud` to establish the connection.
    - Use `disconnect_from_mud` to close the connection.
    - Use `send_to` to send data to the MUD server.
    - The `mud_read` and `mud_write` methods handle reading from and writing to the
        server.

Classes:
    - `MudConnection`: Manages the connection to a MUD server.
"""

# Standard Library
import asyncio
import collections
import datetime
import logging
import re
import zlib
from typing import TYPE_CHECKING, Any, NamedTuple

# Third Party
from telnetlib3 import TelnetReaderUnicode, open_connection
from telnetlib3.client import TelnetClient
from telnetlib3.telopt import CMD_EOR, GA, MCCP3_COMPRESS

from bastproxy.libs.api import API
from bastproxy.libs.asynch import TaskItem
from bastproxy.libs.logger import get_logger
from bastproxy.libs.net.negotiation import RecordingTelnetWriter

# Project
from bastproxy.libs.records import (
    NetworkData,
    NetworkDataLine,
    Originated,
    ProcessDataToClient,
    SendDataDirectlyToClient,
)

logger = get_logger(__name__)

if TYPE_CHECKING:
    from telnetlib3 import TelnetWriterUnicode


class MudConnection:
    """Manage the connection to a MUD server."""

    def __init__(self, addr: str, port: str) -> None:
        """Initialize the connection with the server address and port.

        This constructor sets up the initial state of the connection, including the
        server address, port, API instance, connection status, send queue, connection
        time, and other relevant attributes.

        Args:
            addr: The server address to connect to.
            port: The port number to connect to.

        """
        self.addr: str = addr
        self.port: str = port
        self.api = API(owner_id="libs.net.mud")
        # self.conn_type: str = conn_type
        # self.state: dict[str, bool] = {'connected': True}
        # not connected until the telnet connection opens (#306)
        self.connected = False
        # True from the connect command until the connection opens or fails, so a
        # second connect cannot start another attempt in the meantime (#306)
        self.connecting: bool = False
        self.send_queue: asyncio.Queue[NetworkDataLine] = asyncio.Queue()
        self.connected_time = datetime.datetime.now(datetime.UTC)
        self.reader: MudTelnetReader | None = None
        self.writer: TelnetWriterUnicode | None = None
        self.max_lines_to_process = 15
        self.term_type = "bastproxy"

    async def connect_to_mud(self) -> None:
        """Establish a connection to the MUD server.

        This method initiates a connection to the MUD server using the provided
        address and port. It sets up the reader and writer streams for communication
        and starts the telnet handler for managing the connection.

        If the connection fails (refused, unreachable, timed out) the failure is
        logged, the client is told why and the method returns with `connected`
        left False, so a new connect can be attempted.

        Returns:
            None

        Raises:
            None

        """
        # create a mud connection through telnetlib3
        try:
            await open_connection(
                self.addr,
                int(self.port),
                term=self.term_type,
                shell=self.mud_telnet_handler,
                encoding="utf8",
                client_factory=MudTelnetClient,
                # accept MCCP2 (and MCCP3 when the MUD offers it); the stream is
                # decompressed before MudTelnetReader sees it (ADR-0001, #58).
                compression=True,
                # without BINARY negotiated telnetlib3 5.x decodes as US-ASCII
                # regardless of encoding; force utf8 (#63).
                force_binary=True,
            )
        except OSError as exc:
            self.connected = False
            self.connecting = False
            logger.error("Could not connect to the mud at %s:%s: %s", self.addr, self.port, exc)
            SendDataDirectlyToClient(
                NetworkData([f"Could not connect to the mud at {self.addr}:{self.port}: {exc}"])
            )()
        except BaseException:
            # a bad port, a cancelled task: never leave the flag stuck
            self.connecting = False
            raise

    def disconnect_from_mud(self) -> None:
        """Disconnect from the MUD server.

        This method updates the connection status to indicate that the client is no
        longer connected.

        Returns:
            None

        Raises:
            None

        """
        self.connected = False
        self.connecting = False

    def send_to(self, data: NetworkDataLine) -> None:
        """Send data to the MUD server.

        This method places the provided data into the send queue for transmission
        to the MUD server. If the connection is not active, it logs an error message
        and does not send the data.

        Args:
            data: The data to send to the MUD server.

        Returns:
            None

        Raises:
            None

        """
        if not self.connected:
            logger.debug("send_to - Not connected to the mud, cannot send data")
            return
        loop = asyncio.get_event_loop()
        if not isinstance(data, NetworkDataLine):
            logger.error(
                "client: send_to - got a type that is not NetworkDataLine: %s",
                type(data),
                stack_info=True,
            )
        else:
            loop.call_soon_threadsafe(self.send_queue.put_nowait, data)

    async def setup_mud(self) -> None:
        """Set up the MUD connection with initial configurations.

        This method ensures that the writer stream is drained after the connection
        is established.

        Returns:
            None

        Raises:
            None

        """
        if self.writer:
            await self.writer.drain()

    async def mud_read(self) -> None:
        """Read data from the MUD server.

        This method continuously reads data from the MUD server while the connection
        is active. It processes the received data, logs it, and handles end-of-file
        conditions. The method ensures that the data is read in chunks and processed
        appropriately, including handling partial lines and EOF scenarios.

        Returns:
            None

        Raises:
            None

        """
        logger.info("mud_read - Starting coroutine for mud")

        while self.connected and self.reader:
            data = NetworkData([], owner_id="mud_read")
            while True:
                rec = await self.reader.read_mud_line()
                if not rec.text:
                    break
                logger.debug("mud_read - Raw received data in mud_read : %r", rec)
                line = NetworkDataLine(
                    rec.text.rstrip() if rec.ended else rec.text,
                    originated=Originated.MUD,
                    had_line_endings=rec.ended,
                )
                line.is_prompt = rec.prompt
                data.append(line)
                logging.getLogger("data.mud").info("%-12s : %s", "from_mud", rec.text)
                if not self.reader.line_ready() or len(data) >= self.max_lines_to_process:
                    break

            if self.reader.at_eof():  # This is an EOF.  Hard disconnect.
                # lines read in the same pass as the EOF must still reach the client
                if len(data) > 0:
                    ProcessDataToClient(data)()
                self.connected = False
                return

            # this is where we start with process data
            ProcessDataToClient(data)()

            # this is so we don't hog the asyncio loop
            await asyncio.sleep(0)

        logger.info("mud_read - Ending coroutine")

    async def mud_write(self) -> None:
        """Write data to the MUD server.

        This method continuously retrieves data from the send queue and writes it to
        the MUD server while the connection is active. It handles different types of
        messages, including regular data and telnet commands, and ensures that the
        writer stream is properly managed. The method also includes a mechanism to
        prevent overloading the asyncio loop by limiting the number of lines processed
        in each iteration.

        Returns:
            None

        Raises:
            None

        """
        logger.debug("client_write - Starting coroutine for mud_write")
        count = 0
        while self.connected and self.writer and not self.writer.connection_closed:
            msg_obj: NetworkDataLine = await self.send_queue.get()
            count += 1
            if msg_obj.is_io:
                if msg_obj.line:
                    logger.debug("mud_write - Writing message to mud: %s", msg_obj.line)
                    logger.debug("mud_write - type of msg_obj.msg = %s", type(msg_obj.line))
                    self.writer.write(msg_obj.line)
                    msg_obj.was_sent = True
                    logging.getLogger("data.mud").info("%-12s : %s", "to_mud", msg_obj.line)
                else:
                    logger.debug("client_write - No message to write to client.")
            elif msg_obj.is_command_telnet:
                logger.debug("mud_write - type of msg_obj.msg = %s", type(msg_obj.line))
                logger.debug("mud_write - Writing telnet option mud: %r", msg_obj.line)
                self.writer.send_iac(msg_obj.line)
                msg_obj.was_sent = True
                logging.getLogger("data.mud").info("%-12s : %s", "to_mud", msg_obj.line)

            if count >= self.max_lines_to_process:
                await asyncio.sleep(0)
                count = 0

        logger.debug("mud_write - Ending coroutine")

    async def mud_telnet_handler(
        self, reader: "MudTelnetReader", writer: "TelnetWriterUnicode"
    ) -> None:
        """Handle the telnet connection for the MUD server.

        This method sets up the telnet connection by initializing the reader and
        writer streams, setting up the necessary tasks for reading and writing data,
        and configuring the telnet handler. It also manages the connection lifecycle,
        including handling connection opening and closing events.

        Args:
            reader: The stream reader for the telnet connection.
            writer: The stream writer for the telnet connection.

        Returns:
            None

        Raises:
            None

        """
        client_details: str = writer.get_extra_info("peername")

        _, _, *rest = client_details
        logger.warning("Mud Connection opened - %s : %s : %s", self.addr, self.port, rest)
        self.connected = True
        self.connecting = False
        self.connected_time = datetime.datetime.now(datetime.UTC)
        self.reader = reader
        self.writer = writer
        # milliseconds in the setting; a change applies to the next connection
        reader.line_timeout = (
            self.api("plugins.core.settings:setting.get")("plugins.core.proxy", "mudlinewait")
            / 1000
        )

        tasks: list[asyncio.Task] = [
            TaskItem(self.mud_read(), name="mud telnet read").create(),
            TaskItem(self.mud_write(), name="mud telnet write").create(),
        ]

        if current_task := asyncio.current_task():
            current_task.set_name("mud telnet client handler")

        await self.setup_mud()

        _, rest = await asyncio.wait(tasks, return_when="FIRST_COMPLETED")

        for task in rest:
            task.cancel()

        self.connected = False

        logger.warning("Mud Connection closed - %s : %s : %s", self.addr, self.port, rest)
        SendDataDirectlyToClient(NetworkData(["Connection to the mud has been closed."]))()

        await asyncio.sleep(1)


class MudLine(NamedTuple):
    """One unit of MUD output read by `MudTelnetReader.read_mud_line`.

    Attributes:
        text: The decoded text, with its terminator. A ``\\r\\0`` ending is
            trimmed to ``\\r``. Empty only at EOF with nothing left to read.
        ended: True when the text ends in a line ending. False for a partial
            line, such as a prompt with no line ending.
        prompt: True when an IAC GA or IAC EOR followed the text.

    """

    text: str
    ended: bool
    prompt: bool


# A line ending, leftmost first, preferring the two byte endings. A lone CR or
# LF counts only when another byte follows it: the byte after it may be the
# other half of "\r\n" or "\n\r" that a later packet carries (#65).
_LINE_END = re.compile(rb"\r\n|\n\r|\r\x00|\r(?=[^\n\x00])|\n(?=[^\r])")
# The same, but a lone CR or LF at the very end of the data also counts. Used
# once waiting for the other half has timed out, and below a prompt mark.
_LINE_END_FINAL = re.compile(rb"\r\n|\n\r|\r\x00|\r(?=[^\n\x00]|\Z)|\n(?=[^\r]|\Z)")


class MudTelnetReader(TelnetReaderUnicode):
    r"""Telnet reader that splits MUD output into lines without phantom blanks.

    A line ends at CR LF, LF CR, CR NUL, or a lone CR or LF followed by another
    byte. When the data ends in a lone CR or LF, or holds text with no ending,
    the reader waits up to ``line_timeout`` seconds for more bytes before it
    delivers what it holds, so a ``\n\r`` split across two packets is one
    ending, not a line and a blank line. Each new chunk restarts the wait.

    ``mark_prompt`` records a prompt boundary at the end of the data received
    so far; the bytes up to it are delivered at once with ``prompt=True``.

    Do not mix ``read()`` or ``readexactly()`` with ``read_mud_line``: they do
    not know about the prompt marks.
    """

    line_timeout: float = 0.1

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        """Initialize the reader with no prompt marks."""
        super().__init__(*args, **kwargs)
        self._prompt_marks: collections.deque[int] = collections.deque()

    def mark_prompt(self, cmd: bytes) -> None:
        """Mark the end of the buffered data as a prompt (IAC GA or IAC EOR).

        Args:
            cmd: The telnet command that triggered the mark.

        """
        del cmd
        if not self._buffer:
            return
        if not self._prompt_marks or self._prompt_marks[-1] != len(self._buffer):
            self._prompt_marks.append(len(self._buffer))
        self._wakeup_waiter()

    def line_ready(self) -> bool:
        """Return True when `read_mud_line` can return without waiting."""
        return bool(self._prompt_marks) or _LINE_END.search(self._buffer) is not None

    def _consume(self, end: int, keep: int, *, ended: bool) -> MudLine:
        """Remove the first ``end`` bytes and return them as a `MudLine`."""
        raw = bytes(self._buffer[:keep])
        prompt = any(mark == end for mark in self._prompt_marks)
        del self._buffer[:end]
        self._prompt_marks = collections.deque(m - end for m in self._prompt_marks if m > end)
        self._maybe_resume_transport()
        return MudLine(self.decode(raw), ended, prompt)

    def _take_complete(self) -> MudLine | None:
        """Return the next line that is complete without waiting, or None."""
        if self._prompt_marks:
            mark = self._prompt_marks[0]
            match = _LINE_END_FINAL.search(self._buffer, 0, mark)
            if match is None:
                return self._consume(mark, mark, ended=False)
        else:
            match = _LINE_END.search(self._buffer)
            if match is None:
                return None
        return self._consume_match(match)

    def _consume_match(self, match: re.Match[bytes]) -> MudLine:
        """Consume up to the end of a matched line ending."""
        end = match.end()
        keep = end - 1 if match.group() == b"\r\x00" else end
        return self._consume(end, keep, ended=True)

    def _take_pending(self) -> MudLine:
        """Return what the buffer holds when no more bytes are coming in time."""
        if not self._buffer:
            return MudLine("", False, False)
        match = _LINE_END_FINAL.search(self._buffer)
        if match is not None:
            return self._consume_match(match)
        return self._consume(len(self._buffer), len(self._buffer), ended=False)

    async def read_mud_line(self) -> MudLine:
        """Read the next line, partial line or prompt.

        Returns:
            The `MudLine`. Its text is empty only at EOF with nothing left.

        Raises:
            Exception: The exception set on the reader, if any.

        """
        while True:
            if (exc := self.exception()) is not None:
                raise exc
            if (line := self._take_complete()) is not None:
                return line
            if self._eof:
                return self._take_pending()
            if not self._buffer:
                await self._wait_for_data("read_mud_line")
                continue
            try:
                async with asyncio.timeout(self.line_timeout):
                    await self._wait_for_data("read_mud_line")
            except TimeoutError:
                return self._take_pending()

    async def readline(self) -> str:
        """Read one line and return its text, for callers that want a str."""
        return (await self.read_mud_line()).text


#: Most bytes one received chunk of an MCCP2 stream may inflate to. An asyncio socket read is at
#: most 256 KiB (``_SelectorSocketTransport.max_size``), and MUD text compresses about 10 to 20
#: to 1, so a full read inflates to a few MiB. 16 MiB allows 64 to 1 on a full read; zlib can
#: reach about 1000 to 1, which this stops.
MCCP2_MAX_INFLATED_CHUNK = 16 * 1024 * 1024


class _BoundedDecompressor:
    """Wrap a zlib decompressor so one chunk cannot inflate past ``MCCP2_MAX_INFLATED_CHUNK``.

    telnetlib3 calls ``decompress`` with no output limit. An over-limit chunk raises
    ``zlib.error``, which telnetlib3 treats as a broken stream.
    """

    def __init__(self, inner: Any) -> None:
        """Wrap *inner*, a ``zlib.decompressobj`` result."""
        self._inner = inner

    def decompress(self, data: bytes) -> bytes:
        """Inflate *data*, raising ``zlib.error`` when the output exceeds the limit."""
        limit = MCCP2_MAX_INFLATED_CHUNK
        out: bytes = self._inner.decompress(data, limit + 1)
        if len(out) > limit or self._inner.unconsumed_tail:
            raise zlib.error("chunk exceeded the inflation limit")
        return out

    def __getattr__(self, name: str) -> Any:
        """Forward ``eof``, ``unused_data`` and the rest to the wrapped decompressor."""
        return getattr(self._inner, name)


class MudTelnetClient(TelnetClient):
    """telnetlib3 client for the MUD side that declines GMCP and ZMP.

    telnetlib3 5.x enables GMCP/ZMP and sends Core.Hello on the proxy's behalf.
    Until the protocol handling is decided (ADR-0001, #40) keep the 2.0.4
    behavior of not negotiating them (#39).

    It also accepts MCCP2 and MCCP3 (#58). telnetlib3 decompresses the MUD's
    stream; the overrides below cover what telnetlib3 5.0.2 gets wrong:

    - after a decompression error it passes every later compressed byte on as
      text. Here a broken stream sets ``mccp2_failed``, drops all later bytes
      and closes the MUD link.
    - its raw-deflate retry can start a new decompressor partway through a
      stream. Here the retry is limited to the first chunk of a stream.
    - it inflates a received chunk without a size limit. Here a chunk that inflates past
      ``MCCP2_MAX_INFLATED_CHUNK`` counts as a broken stream.
    - ``WONT MCCP3`` from the MUD never stops its compression of our writes.
    """

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        """Initialize the client with no MCCP2 failure."""
        self._bounded_mccp2: _BoundedDecompressor | None = None
        super().__init__(*args, **kwargs)
        self.mccp2_failed: bool = False

    @property
    def _mccp2_decompressor(self) -> Any:
        """The MCCP2 decompressor, bounded per chunk, or None."""
        return self._bounded_mccp2

    @_mccp2_decompressor.setter
    def _mccp2_decompressor(self, value: Any) -> None:
        """Wrap each decompressor telnetlib3 assigns, including its raw-deflate retry."""
        self._bounded_mccp2 = None if value is None else _BoundedDecompressor(value)

    def _mccp2_end(self) -> None:
        """End MCCP2 decompression; a stream that did not end cleanly closes the link."""
        decompressor = self._mccp2_decompressor
        broken = decompressor is not None and not decompressor.eof
        super()._mccp2_end()
        if broken:
            self.mccp2_failed = True
            logger.error(
                "MCCP2 decompression error on the mud link (a broken stream or a chunk over the "
                "inflation limit), closing the connection to the mud"
            )
            self.writer.close()

    def _process_chunk(self, data: bytes) -> bool:
        """Process a chunk, dropping data after a failed stream and ending MCCP3 on WONT."""
        if self.mccp2_failed:
            return False
        result = super()._process_chunk(data)
        if self._mccp2_decompressor is not None:
            # a later error is a broken stream, not a stream in raw deflate form
            self._mccp2_wbits_fallback = True
        if self._mccp3_compressor is not None and not self.writer.remote_option.enabled(
            MCCP3_COMPRESS
        ):
            self._mccp3_end()
        return result

    def setup_gmcp(self) -> None:
        """Do not negotiate GMCP (see #39, #40)."""

    def setup_zmp(self) -> None:
        """Do not negotiate ZMP (see #39, #40)."""

    _reader_factory_encoding = MudTelnetReader
    _writer_factory_encoding = RecordingTelnetWriter

    def connection_made(self, transport: asyncio.BaseTransport) -> None:
        """Register the prompt marks (IAC GA and IAC EOR) once the reader exists."""
        super().connection_made(transport)
        for cmd in (GA, CMD_EOR):
            self.writer.set_iac_callback(cmd, self.reader.mark_prompt)
