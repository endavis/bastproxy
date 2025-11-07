# Project: bastproxy
# Filename: libs/net/client.py
#
# File Description: Client connection handling.
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
import datetime
import logging
from typing import TYPE_CHECKING

# Third Party
from telnetlib3 import open_connection

from libs.api import API
from libs.asynch import TaskItem

# Project
from libs.net import telnet
from libs.records import (
    LogRecord,
    NetworkDataLine,
    ProcessDataToClient,
    SendDataDirectlyToClient,
    SendDataDirectlyToMud,
)
from libs.records import NetworkData as NetworkData

if TYPE_CHECKING:
    from telnetlib3 import TelnetReaderUnicode, TelnetWriterUnicode


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
        self.api = API(owner_id=f"{__name__}")
        # self.conn_type: str = conn_type
        # self.state: dict[str, bool] = {'connected': True}
        self.connected = True
        self.send_queue: asyncio.Queue[NetworkDataLine] = asyncio.Queue()
        self.connected_time = datetime.datetime.now(datetime.UTC)
        self.reader: TelnetReaderUnicode | None = None
        self.writer: TelnetWriterUnicode | None = None
        self.max_lines_to_process = 15
        self.term_type = "bastproxy"
        # rows = self.writer.protocol._extra['rows']
        # term = self.writer.protocol._extra['TERM']

    async def connect_to_mud(self) -> None:
        """Establish a connection to the MUD server.

        This method initiates a connection to the MUD server using the provided
        address and port. It sets up the reader and writer streams for communication
        and starts the telnet handler for managing the connection.

        Returns:
            None

        Raises:
            ConnectionError: If the connection to the MUD server fails.

        """
        # create a mud connection through telnetlib3
        await open_connection(
            self.addr,
            int(self.port),
            term=self.term_type,
            shell=self.mud_telnet_handler,
            encoding="utf8",
        )

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
            LogRecord(
                "send_to - Not connected to the mud, cannot send data",
                level="debug",
                sources=[__name__],
            )()
            return
        loop = asyncio.get_event_loop()
        if not isinstance(data, NetworkDataLine):
            LogRecord(
                "client: send_to - got a type that is not NetworkDataLine: "
                f"{type(data)}",
                level="error",
                stack_info=True,
                sources=[__name__],
            )()
        else:
            loop.call_soon_threadsafe(self.send_queue.put_nowait, data)

    async def setup_mud(self) -> None:
        """Set up the MUD connection with initial configurations.

        This method advertises telnet features to the MUD server and sends them
        using the `SendDataDirectlyToMud` method. It also ensures that the writer
        stream is properly drained after sending the features.

        Returns:
            None

        Raises:
            None

        """
        if features := telnet.advertise_features():
            LogRecord(
                "setup_mud - Sending telnet features",
                level="info",
                sources=[__name__],
            )()
            networkdata = NetworkData([], owner_id="mud:setup_mud")
            networkdata.append(
                NetworkDataLine(
                    features, originated="internal", line_type="COMMAND-TELNET"
                )
            )
            SendDataDirectlyToMud(networkdata)()
            LogRecord(
                "setup_mud - telnet features sent",
                level="info",
                sources=[__name__],
            )()

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
        LogRecord(
            "mud_read - Starting coroutine for mud",
            level="info",
            sources=[__name__],
        )()

        while self.connected and self.reader:
            inp: str = ""

            data = NetworkData([], owner_id="mud_read")
            while True:
                inp = await self.reader.readline()
                if not inp:
                    print("no data from readline")
                    break
                LogRecord(
                    f"client_read - readline - Raw received data in mud_read : {inp}",
                    level="debug",
                    sources=[__name__],
                )()
                LogRecord(
                    f"client_read - readline - inp type = {type(inp)}",
                    level="debug",
                    sources=[__name__],
                )()
                data.append(NetworkDataLine(inp.rstrip(), originated="mud"))
                logging.getLogger("data.mud").info(f"{'from_mud':<12} : {inp}")
                if (
                    len(self.reader._buffer) <= 0
                    or b"\n" not in self.reader._buffer
                    or len(data) == self.max_lines_to_process
                ):
                    break

            if len(self.reader._buffer) > 0 and b"\n" not in self.reader._buffer:
                inp: str = await self.reader.read(len(self.reader._buffer))
                LogRecord(
                    f"client_read - read - Raw received data in mud_read : {inp}",
                    level="debug",
                    sources=[__name__],
                )()
                LogRecord(
                    f"client_read - read - inp type = {type(inp)}",
                    level="debug",
                    sources=[__name__],
                )()
                data.append(
                    NetworkDataLine(inp, originated="mud", had_line_endings=False)
                )
                logging.getLogger("data.mud").info(f"{'from_mud':<12} : {inp}")

            if self.reader.at_eof():  # This is an EOF.  Hard disconnect.
                self.connected = False
                return

            # this is where we start with process data
            ProcessDataToClient(data)()

            # this is so we don't hog the asyncio loop
            await asyncio.sleep(0)

        LogRecord("mud_read - Ending coroutine", level="info", sources=[__name__])()

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
        LogRecord(
            "client_write - Starting coroutine for mud_write",
            level="debug",
            sources=[__name__],
        )()
        count = 0
        while self.connected and self.writer and not self.writer.connection_closed:
            msg_obj: NetworkDataLine = await self.send_queue.get()
            count += 1
            if msg_obj.is_io:
                if msg_obj.line:
                    LogRecord(
                        f"mud_write - Writing message to mud: {msg_obj.line}",
                        level="debug",
                        sources=[__name__],
                    )()
                    LogRecord(
                        f"mud_write - type of msg_obj.msg = {type(msg_obj.line)}",
                        level="debug",
                        sources=[__name__],
                    )()
                    self.writer.write(msg_obj.line)
                    msg_obj.was_sent = True
                    logging.getLogger("data.mud").info(
                        f"{'to_mud':<12} : {msg_obj.line}"
                    )
                else:
                    LogRecord(
                        "client_write - No message to write to client.",
                        level="debug",
                        sources=[__name__],
                    )()
            elif msg_obj.is_command_telnet:
                LogRecord(
                    f"mud_write - type of msg_obj.msg = {type(msg_obj.line)}",
                    level="debug",
                    sources=[__name__],
                )()
                LogRecord(
                    f"mud_write - Writing telnet option mud: {repr(msg_obj.line)}",
                    level="debug",
                    sources=[__name__],
                )()
                self.writer.send_iac(msg_obj.line)
                msg_obj.was_sent = True
                logging.getLogger("data.mud").info(
                    f"{'to_client':<12} : {msg_obj.line}"
                )

            if count >= self.max_lines_to_process:
                await asyncio.sleep(0)
                count = 0

        LogRecord("mud_write - Ending coroutine", level="debug", sources=[__name__])()

    async def mud_telnet_handler(
        self, reader: "TelnetReaderUnicode", writer: "TelnetWriterUnicode"
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
        LogRecord(
            f"Mud Connection opened - {self.addr} : {self.port} : {rest}",
            level="warning",
            sources=[__name__],
        )()
        self.reader = reader
        self.writer = writer
        self.reader.readline = unicode_readline_monkeypatch.__get__(reader)

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

        LogRecord(
            f"Mud Connection closed - {self.addr} : {self.port} : {rest}",
            level="warning",
            sources=[__name__],
        )()
        SendDataDirectlyToClient(
            NetworkData(["Connection to the mud has been closed."])
        )()

        await asyncio.sleep(1)


async def unicode_readline_monkeypatch(self) -> str:
    r"""Read one line.

    Where "line" is a sequence of characters ending with CR LF, LF,
    or CR NUL. This readline function is a strict interpretation of
    Telnet Protocol :rfc:`854`.

    The sequence "CR LF" must be treated as a single "new line" character
    and used whenever their combined action is intended; The sequence "CR
    NUL" must be used where a carriage return alone is actually desired;
    and the CR character must be avoided in other contexts.

    And therefor, a line does not yield for a stream containing a
    CR if it is not succeeded by NUL or LF.

    ================= =====================
    Given stream      readline() yields
    ================= =====================
    ``--\r\x00---``   ``--\r``, ``---`` *...*
    ``--\r\n---``     ``--\r\n``, ``---`` *...*
    ``--\n---``       ``--\n``, ``---`` *...*
    ``--\r---``       ``--\r``, ``---`` *...*
    ================= =====================

    If EOF is received before the termination of a line, the method will
    yield the partially read string.

    Note: this is a monkey-patch of the TelnetReaderUnicode.readline method
    to support \n\r line endings.
    """
    if self._exception is not None:
        raise self._exception

    line = bytearray()
    not_enough = True

    while not_enough:
        while self._buffer and not_enough:
            search_results_pos_kind = (
                (self._buffer.find(b"\r\n"), b"\r\n"),
                (self._buffer.find(b"\n\r"), b"\n\r"),
                (self._buffer.find(b"\r\x00"), b"\r\x00"),
                (self._buffer.find(b"\r"), b"\r"),
                (self._buffer.find(b"\n"), b"\n"),
            )

            # sort by (position, length * -1), so that the
            # smallest sorted value is the longest-match,
            # preferring '\r\n' over '\r', for example.
            matches = [
                (_pos, len(_kind) * -1, _kind)
                for _pos, _kind in search_results_pos_kind
                if _pos != -1
            ]

            if not matches:
                line.extend(self._buffer)
                self._buffer.clear()
                continue

            # position is nearest match,
            pos, _, kind = min(matches)
            if kind == b"\r\x00":
                # trim out '\x00'
                begin, end = pos + 1, pos + 2
            elif kind in [b"\r\n", b"\n\r"]:
                begin = end = pos + 2
            else:
                # '\r' or '\n'
                begin = end = pos + 1
            line.extend(self._buffer[:begin])
            del self._buffer[:end]
            not_enough = False

        if self._eof:
            break

        if not_enough:
            await self._wait_for_data("readline")

    self._maybe_resume_transport()
    buf = bytes(line)
    return self.decode(buf)
