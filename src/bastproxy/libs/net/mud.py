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
from collections.abc import Sequence
from typing import TYPE_CHECKING, Any, NamedTuple, cast

# Third Party
from telnetlib3 import TelnetReaderUnicode, open_connection
from telnetlib3.client import TelnetClient
from telnetlib3.telopt import CMD_EOR, ECHO, GA, GMCP, MSDP, MSSP, MXP, SGA, TTYPE

from bastproxy.libs.api import API
from bastproxy.libs.asynch import TaskItem
from bastproxy.libs.logger import echo_off_placeholder, get_logger
from bastproxy.libs.net import mtts
from bastproxy.libs.net.naws import WINDOW_SIZE
from bastproxy.libs.net.negotiation import RecordingTelnetWriter, option_names
from bastproxy.libs.net.protocols import PROTOCOLS

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
        self.protocol: MudTelnetClient | None = None
        self.lines_sent: int = 0
        self.lines_received: int = 0
        self.max_lines_to_process = 15
        # not forwarded from the client: the proxy's own terminal type (#308), answered
        # with the MTTS cycle (#547)
        self.term_type = mtts.TERMINAL_TYPE

    @property
    def bytes_sent(self) -> int:
        """Return the uncompressed telnet bytes written to the mud link (0 without a link)."""
        return 0 if self.protocol is None else self.protocol.tx_bytes

    @property
    def bytes_received(self) -> int:
        """Return the uncompressed telnet bytes read from the mud link (0 without a link)."""
        return 0 if self.protocol is None else self.protocol.rx_bytes

    @property
    def idle(self) -> str:
        """Return how long the mud link has been silent, in a human-readable format.

        Returns:
            The idle time, or ``-`` when there is no link.

        """
        if self.protocol is None:
            return "-"
        now = datetime.datetime.now(datetime.UTC)
        idle = datetime.timedelta(seconds=float(self.protocol.idle))
        return cast(str, self.api("plugins.core.utils:timedelta.to.string")(now - idle, now))

    def telnet_options(self) -> tuple[list[str], list[str]]:
        """Return the enabled (local, remote) option names on the mud link."""
        if self.writer is None:
            return [], []
        return option_names(self.writer.local_option), option_names(self.writer.remote_option)

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
                shell=self.mud_telnet_handler,  # type: ignore[arg-type]  # handler takes the reader and writer our factories build
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

    @property
    def echo_off(self) -> bool:
        """True while the MUD has WILL ECHO in effect on this link."""
        return self.writer is not None and self.writer.remote_option.enabled(ECHO) is True

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

    def send_to(self, data: object) -> None:
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
                writer = self.writer
                line.mxp_mode = PROTOCOLS.mxp_line_mode(
                    rec.text,
                    ended=rec.ended,
                    enabled=writer is not None and writer.remote_option.enabled(MXP) is True,
                )
                data.append(line)
                self.lines_received += 1
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
                    shown = (
                        echo_off_placeholder(msg_obj.line)
                        if self.echo_off or msg_obj.mask_log
                        else msg_obj.line
                    )
                    logger.debug("mud_write - Writing message to mud: %s", shown)
                    logger.debug("mud_write - type of msg_obj.msg = %s", type(msg_obj.line))
                    self.writer.write(cast(str, msg_obj.line))
                    msg_obj.was_sent = True
                    self.lines_sent += 1
                    logging.getLogger("data.mud").info("%-12s : %s", "to_mud", shown)
                else:
                    logger.debug("client_write - No message to write to client.")
            elif msg_obj.is_command_telnet:
                logger.debug("mud_write - type of msg_obj.msg = %s", type(msg_obj.line))
                logger.debug("mud_write - Writing telnet option mud: %r", msg_obj.line)
                self.writer.send_iac(cast(bytes, msg_obj.line))
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
        client_details: tuple[Any, ...] = writer.get_extra_info("peername")

        _, _, *rest = client_details
        logger.warning("Mud Connection opened - %s : %s : %s", self.addr, self.port, rest)
        self.connected = True
        self.connecting = False
        self.connected_time = datetime.datetime.now(datetime.UTC)
        self.reader = reader
        self.writer = writer
        self.protocol = writer.protocol
        PROTOCOLS.mud_connected(writer)
        WINDOW_SIZE.mud_connected(writer)
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

        try:
            await self.setup_mud()

            _, pending = await asyncio.wait(tasks, return_when="FIRST_COMPLETED")

            for task in pending:
                task.cancel()
        finally:
            PROTOCOLS.mud_disconnected()
            WINDOW_SIZE.mud_disconnected()

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

    async def readline(self) -> str:  # type: ignore[override]  # returns str, the base returns bytes
        """Read one line and return its text, for callers that want a str."""
        return (await self.read_mud_line()).text


class MudTelnetClient(TelnetClient):
    """telnetlib3 client for the MUD side that terminates GMCP, MSDP and MSSP and declines ZMP.

    GMCP, MSDP and MSSP are accepted and decoded by the proxy (ADR-0001, #59, #60); the proxy
    sends its
    own ``Core.Hello`` instead of telnetlib3's. ZMP is not negotiated (#39).

    It also accepts MCCP2 and MCCP3 (#58). telnetlib3 5.0.3 decompresses the MUD's stream in
    1 MiB steps, closes the link after a decompression error, ends MCCP2 on ``WONT MCCP2`` and
    ends MCCP3 on ``WONT MCCP3``. One override remains:

    - telnetlib3 retries with raw deflate after the first ``zlib.error`` at any point in a
      stream. Here the retry is limited to the first chunk of a stream.

    ``tx_bytes`` and ``rx_bytes`` count the telnet stream with negotiation, uncompressed (#422).

    SGA is refused (``DONT SGA``) so the MUD keeps sending ``IAC GA`` after prompts (#271).

    ``send_naws`` answers ``DO NAWS`` with the size ``WINDOW_SIZE`` chose (#308); later changes
    are sent by ``WINDOW_SIZE`` itself with ``send_iac``.

    TTYPE is answered with the MTTS cycle of the proxy itself: ``BASTPROXY``, then
    ``ANSI-256COLOR``, then ``MTTS 525``, which repeats; ``IAC DONT TTYPE`` starts the cycle
    again. NEW_ENVIRON requests get the MNES variables (``CLIENT_NAME``, ``CLIENT_VERSION``,
    ``TERMINAL_TYPE``, ``MTTS``, ``CHARSET``) and an empty variable name is ignored (#547).
    """

    # telnetlib3 types these as optional; they are set once connected (annotation only)
    reader: MudTelnetReader
    writer: RecordingTelnetWriter
    _ttype_cycle: mtts.TtypeCycle

    # telnetlib3's writer adds every byte it writes to ``_tx_bytes`` when its protocol has the
    # attribute (``hasattr(protocol, "_tx_bytes")``); the count is taken before MCCP3 compresses.
    _tx_bytes: int = 0
    # bytes of the telnet stream received, after MCCP2 inflation (see ``_trace_recv``)
    rx_total: int = 0

    @property
    def tx_bytes(self) -> int:
        """Return the bytes written to the mud, before MCCP3 compression."""
        return self._tx_bytes

    @property
    def rx_bytes(self) -> int:
        """Return the bytes of the telnet stream received, after MCCP2 inflation."""
        return self.rx_total

    def _trace_recv(self, data: bytes, decompressed: bool = False) -> None:
        """Count the received bytes, then let telnetlib3 trace them.

        telnetlib3 calls this once for each plain or inflated segment, and for the chunk that
        turns MCCP2 on only for its plain prefix. ``data_received`` would count compressed
        bytes, and ``_process_chunk`` would count the compressed tail of that chunk twice.
        """
        self.rx_total += len(data)
        super()._trace_recv(data, decompressed)

    def send_naws(self) -> tuple[int, int]:
        """Return (rows, cols) for the reply to ``DO NAWS`` (#308)."""
        return WINDOW_SIZE.mud_reply()

    def send_ttype(self) -> str:
        """Return the answer to the next ``SB TTYPE SEND`` (#547)."""
        return self._ttype_cycle.next()

    def send_env(self, keys: Sequence[str]) -> dict[str, Any]:
        """Return the NEW_ENVIRON values for ``keys``, with the MNES variables answered (#547).

        Empty names, which ``SEND VAR`` and ``SEND USERVAR`` without a name produce, are
        dropped. With no name left every variable is sent; otherwise each requested name gets
        the MNES value or, for any other name, the value the base class gives.
        """
        wanted = [key for key in keys if key]
        mnes = mtts.mnes_variables()
        if not wanted:
            return {**super().send_env([]), **mnes}
        others = [key for key in wanted if key not in mnes]
        base = super().send_env(others) if others else {}
        return {key: mnes[key] if key in mnes else base[key] for key in wanted}

    def _on_mud_dont(self, opt: bytes) -> None:
        """Start the TTYPE cycle again when the MUD sends ``IAC DONT TTYPE`` (#547)."""
        if opt == TTYPE:
            self._ttype_cycle.reset()

    def _process_chunk(self, data: bytes) -> bool:
        """Process a chunk, keeping telnetlib3's raw-deflate retry to the first chunk."""
        result = super()._process_chunk(data)
        if self._mccp2_decompressor is not None:
            # a later error is a broken stream, not a stream in raw deflate form
            self._mccp2_wbits_fallback = True
        return result

    def setup_gmcp(self) -> None:
        """Accept GMCP, MSDP, MSSP and MXP and wire them to the protocol manager (#59, #60, #61).

        MXP markup is ordinary text; the SB MXP start is only logged, so telnetlib3 does not
        keep it in ``ctx.mxp_data``.

        telnetlib3's own ``Core.Hello`` handshake is not used: the manager sends the proxy's
        own once the MUD offers GMCP. This does not call ``super()``.
        """
        self.writer.passive_do.update({GMCP, MSDP, MSSP, MXP})
        self.writer.set_ext_callback(GMCP, PROTOCOLS.on_mud_gmcp)
        self.writer.set_ext_callback(MSDP, PROTOCOLS.on_mud_msdp)
        self.writer.set_ext_callback(MSSP, PROTOCOLS.on_mud_mssp)
        self.writer.set_ext_callback(MXP, PROTOCOLS.on_mud_mxp)
        self.writer.add_will_callback(GMCP, PROTOCOLS.on_mud_will_gmcp)

    def setup_zmp(self) -> None:
        """Do not negotiate ZMP (see #39, #40)."""

    _reader_factory_encoding = MudTelnetReader
    _writer_factory_encoding = RecordingTelnetWriter

    def connection_made(self, transport: asyncio.BaseTransport) -> None:
        """Register the prompt marks and refuse SGA once the reader exists.

        ``WILL SGA`` from the MUD gets ``DONT SGA`` (#271): a MUD that is allowed to suppress
        go-ahead stops sending ``IAC GA`` after prompts, and the prompt marks below depend on it.
        """
        super().connection_made(transport)
        self._ttype_cycle = mtts.TtypeCycle(
            mtts.CLIENT_NAME, self._extra["term"], mtts.PROXY_CAPABILITIES.bitvector
        )
        self.writer.dont_callback = self._on_mud_dont
        self.writer.always_dont.add(SGA)
        for cmd in (GA, CMD_EOR):
            self.writer.set_iac_callback(cmd, self.reader.mark_prompt)
