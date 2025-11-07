# Project: bastproxy
# Filename: libs/net/client.py
#
# File Description: Client connection handling.
#
# By: Bast/Jubelo
"""Module for handling client connections in the bastproxy project.

This module provides the `ClientConnection` class and several utility functions for
managing client connections, including registration, unregistration, and handling of
telnet clients. It includes methods for sending and receiving data, processing login
attempts, and managing client states.

Key Components:
    - ClientConnection: A class that represents a client connection and handles
        communication.
    - register_client: Function to register a new client connection.
    - unregister_client: Function to unregister a client connection.
    - client_telnet_handler: Function to handle new telnet client connections.

Features:
    - Management of client connection states and login attempts.
    - Sending and receiving data through telnet connections.
    - Logging and tracking of client activities.
    - Handling of view-only client connections.
    - Registration and unregistration of client connections.

Usage:
    - Instantiate `ClientConnection` to create a new client connection.
    - Use `register_client` to register a new client connection.
    - Use `unregister_client` to unregister a client connection.
    - Use `client_telnet_handler` to handle new telnet client connections.

Classes:
    - `ClientConnection`: Represents a class that handles client connections.

"""

# Standard Library
import asyncio
import contextlib
import datetime
import logging
from typing import TYPE_CHECKING
from uuid import uuid4

# Third Party
from telnetlib3 import TelnetReaderUnicode, TelnetWriterUnicode

if TYPE_CHECKING:
    from telnetlib3 import TelnetServer

# Project
from libs.api import API
from libs.asynch import TaskItem
from libs.net import telnet
from libs.records import (
    LogRecord,
    NetworkData,
    NetworkDataLine,
    ProcessDataToMud,
    SendDataDirectlyToClient,
)


class ClientConnection:
    """Represents a client connection and handles communication."""

    def __init__(
        self,
        addr: str,
        port: str,
        conn_type: str,
        reader: TelnetReaderUnicode,
        writer: TelnetWriterUnicode,
        rows: int = 24,
    ) -> None:
        """Initialize a client connection.

        This constructor initializes the client connection with the provided address,
        port, connection type, reader, writer, and optional number of rows.

        Args:
            addr: The address of the client.
            port: The port of the client.
            conn_type: The type of connection (e.g., telnet).
            reader: The TelnetReaderUnicode instance for reading data.
            writer: The TelnetWriterUnicode instance for writing data.
            rows: The number of rows for the client display (default is 24).

        """
        self.uuid = uuid4().hex
        self.addr: str = addr
        self.port: str = port
        self.rows: int = rows
        self.api = API(owner_id=f"{__name__}:{self.uuid}")
        self.login_attempts: int = 0
        self.conn_type: str = conn_type
        self.connected: bool = True
        self.state: dict[str, bool] = {"logged in": False}
        self.view_only = False
        self.send_queue: asyncio.Queue[NetworkDataLine] = asyncio.Queue()
        self.connected_time = datetime.datetime.now(datetime.UTC)
        self.reader: TelnetReaderUnicode = reader
        self.writer: TelnetWriterUnicode = writer
        self.telnet_server: TelnetServer | None = self.writer.protocol
        self.data_logger = logging.getLogger(f"data.client.{self.uuid}")
        self.max_lines_to_process = 15

    @property
    def connected_length(self) -> str:
        """Calculate the length of time the client has been connected.

        This property calculates the duration for which the client has been connected
        by comparing the current time with the connection start time.

        Returns:
            The duration of the connection in a human-readable format.

        """
        return self.api("plugins.core.utils:convert.timedelta.to.string")(
            self.connected_time, datetime.datetime.now(datetime.UTC)
        )

    def send_to(self, data: NetworkDataLine) -> None:
        """Send data to the client.

        This method sends a `NetworkDataLine` object to the client. If the client is
        not connected, it logs a debug message and returns. Otherwise, it adds the
        data to the send queue to be processed by the `client_write` coroutine.

        Args:
            data: The `NetworkDataLine` object to send.

        Returns:
            None

        Raises:
            None

        """
        if not self.connected:
            LogRecord(
                f"send_to - {self.uuid} [{self.addr}:{self.port}] is not connected. "
                "Cannot send",
                level="debug",
                sources=[__name__],
            )()
            return
        loop = asyncio.get_event_loop()
        if not isinstance(data, NetworkDataLine):
            LogRecord(
                f"client: send_to - {self.uuid}"
                " got a type that is not NetworkDataLine : "
                f"{type(data)}",
                level="error",
                stack_info=True,
                sources=[__name__],
            )()
        else:
            loop.call_soon_threadsafe(self.send_queue.put_nowait, data)

    async def setup_client(self) -> None:
        """Set up the client connection.

        This coroutine sets up the client connection by sending initial telnet commands
        and welcome messages. It sends an echo off command to prevent the client from
        locally echoing the password, advertises telnet features, and sends a welcome
        message prompting the user to enter their password.

        Returns:
            None

        Raises:
            None

        """
        LogRecord(
            f"setup_client - Sending echo on to {self.uuid}",
            level="debug",
            sources=[__name__],
        )()
        # We send an IAC+WILL+ECHO to the client so that
        #  it won't locally echo the password.
        networkdata = NetworkData(
            [
                NetworkDataLine(
                    telnet.echo_on(), line_type="COMMAND-TELNET", prelogin=True
                )
            ],
            owner_id=f"client:{self.uuid}",
        )
        SendDataDirectlyToClient(networkdata, clients=[self.uuid])()

        if features := telnet.advertise_features():
            networkdata = NetworkData(
                [NetworkDataLine(features, line_type="COMMAND-TELNET", prelogin=True)],
                owner_id=f"client:{self.uuid}",
            )
            LogRecord(
                f"setup_client - Sending telnet features to {self.uuid}",
                level="debug",
                sources=[__name__],
            )()
            SendDataDirectlyToClient(networkdata, clients=[self.uuid])()
            LogRecord(
                f"setup_client - telnet features sent to {self.uuid}",
                level="debug",
                sources=[__name__],
            )()

        await self.writer.drain()

        LogRecord(
            f"setup_client - Sending welcome message to {self.uuid}",
            level="debug",
            sources=[__name__],
        )()
        networkdata = NetworkData(
            [NetworkDataLine("Welcome to Bastproxy.", prelogin=True)],
            owner_id=f"client:{self.uuid}",
        )
        networkdata.append(
            NetworkDataLine("Please enter your password.", prelogin=True)
        )
        SendDataDirectlyToClient(networkdata, clients=[self.uuid])()
        self.login_attempts += 1
        LogRecord(
            f"setup_client - welcome message sent to {self.uuid}",
            level="debug",
            sources=[__name__],
        )()

        await self.writer.drain()

    def process_data_from_not_logged_in_client(self, inp) -> None:
        """Process data from a client that is not logged in.

        This method processes the input data from a client that has not yet logged in.
        It checks the input against the default and view-only passwords, handles login
        attempts, and sends appropriate responses to the client.

        Args:
            inp: The input data from the client.

        Returns:
            None

        Raises:
            None

        """
        # sourcery skip: extract-duplicate-method
        dpw = self.api("plugins.core.proxy:ssc.proxypw")()
        vpw = self.api("plugins.core.proxy:ssc.proxypwview")()
        if inp.strip() == dpw:
            networkdata = NetworkData(
                [
                    NetworkDataLine(
                        telnet.echo_off(), line_type="COMMAND-TELNET", prelogin=True
                    )
                ],
                owner_id=f"client:{self.uuid}",
            )
            networkdata.append(NetworkDataLine("You are now logged in.", prelogin=True))
            SendDataDirectlyToClient(networkdata, clients=[self.uuid])()
            self.api("plugins.core.clients:client.logged.in")(self.uuid)
        elif inp.strip() == vpw:
            networkdata = NetworkData(
                [
                    NetworkDataLine(
                        telnet.echo_off(), line_type="COMMAND-TELNET", prelogin=True
                    )
                ],
                owner_id=f"client:{self.uuid}",
            )
            networkdata.append(
                NetworkDataLine(
                    "You are now logged in as view only user.", prelogin=True
                )
            )
            SendDataDirectlyToClient(networkdata, clients=[self.uuid])()
            self.api("plugins.core.clients:client.logged.in.view.only")(self.uuid)

        elif self.login_attempts < 3:
            self.login_attempts = self.login_attempts + 1
            networkdata = NetworkData(
                [NetworkDataLine("Invalid password. Please try again.", prelogin=True)],
                owner_id=f"client:{self.uuid}",
            )
            SendDataDirectlyToClient(networkdata, clients=[self.uuid])()

        else:
            networkdata = NetworkData(
                [NetworkDataLine("Too many login attempts. Goodbye.", prelogin=True)],
                owner_id=f"client:{self.uuid}",
            )
            SendDataDirectlyToClient(networkdata, clients=[self.uuid])()
            LogRecord(
                f"client_read - {self.uuid} [{self.addr}:{self.port}] too many login "
                "attempts. Disconnecting.",
                level="warning",
                sources=[__name__],
            )()
            self.api("plugins.core.clients:client.banned.add")(self.uuid)

    def process_data_from_view_only_client(self, inp) -> None:
        """Process data from a view-only client.

        This method processes the input data from a client that is logged in as a
        view-only user. It sends a message to the client indicating that commands
        cannot be entered in view-only mode.

        Args:
            inp: The input data from the client.

        Returns:
            None

        Raises:
            None

        """
        networkdata = NetworkData(
            [NetworkDataLine("As a view only user, you cannot enter commands")],
            owner_id=f"client:{self.uuid}",
        )
        SendDataDirectlyToClient(networkdata, clients=[self.uuid])()

    async def client_read(self) -> None:
        """Read data from the client.

        This coroutine reads data from the client connection in a loop until the
        connection is closed. It processes the received data based on the client's
        login state and handles view-only clients separately. The data is then
        processed and sent to the appropriate handler.

        Returns:
            None

        Raises:
            BrokenPipeError: If the connection is broken.

        """
        LogRecord(
            f"client_read - Starting coroutine for {self.uuid}",
            level="debug",
            sources=[__name__],
        )()

        count = 0
        while self.connected:
            try:
                inp: str = await self.reader.readline()
                count += 1
            except BrokenPipeError:
                self.connected = False
                continue
            LogRecord(
                f"client_read - Raw received data in client_read : {inp}",
                level="debug",
                sources=[__name__],
            )()
            LogRecord(
                f"client_read - inp type = {type(inp)}",
                level="debug",
                sources=[__name__],
            )()
            self.data_logger.info("%-12s : %s", "client_read", inp)

            if not inp:  # This is an EOF.  Hard disconnect.
                self.connected = False
                return

            if not self.state["logged in"]:
                self.process_data_from_not_logged_in_client(inp)
                continue

            if self.view_only:
                self.process_data_from_view_only_client(inp)
            else:
                # this is where we start processing data
                ProcessDataToMud(
                    NetworkData(
                        NetworkDataLine(inp.strip(), originated="client"),
                        owner_id=f"client:{self.uuid}",
                    ),
                    client_id=self.uuid,
                )()

            if count > self.max_lines_to_process:
                await asyncio.sleep(0)
                count = 0

        LogRecord(
            f"client_read - Ending coroutine for {self.uuid}",
            level="debug",
            sources=[__name__],
        )()

    async def client_write(self) -> None:
        """Write data to the client.

        This coroutine writes data from the send queue to the client connection in a
        loop until the connection is closed. It processes different types of messages,
        including regular messages, telnet commands, and prompts, and sends them to
        the client.

        Returns:
            None

        Raises:
            None

        """
        LogRecord(
            f"client_write - Starting coroutine for {self.uuid}",
            level="debug",
            sources=[__name__],
        )()

        count = 0
        while self.connected and not self.writer.connection_closed:
            msg_obj: NetworkDataLine = await self.send_queue.get()
            if msg_obj.is_io:
                if msg_obj.line:
                    LogRecord(
                        f"client_write - Writing message to client {self.uuid}: "
                        f"{msg_obj.line}",
                        level="debug",
                        sources=[__name__],
                    )()
                    LogRecord(
                        f"client_write - type of msg_obj.msg = {type(msg_obj.line)}",
                        level="debug",
                        sources=[__name__],
                    )()
                    self.writer.write(msg_obj.line)
                    msg_obj.was_sent = True
                    self.data_logger.info("%-12s : %s", "client_write", msg_obj.line)
                else:
                    LogRecord(
                        "client_write - No message to write to client.",
                        level="debug",
                        sources=[__name__],
                    )()
                if msg_obj.is_prompt:
                    self.writer.write(telnet.go_ahead())
                    self.data_logger.info(
                        "%-12s : %s", "client_write", telnet.go_ahead()
                    )
            elif msg_obj.is_command_telnet:
                LogRecord(
                    f"client_write - type of msg_obj.msg = {type(msg_obj.line)}",
                    level="debug",
                    sources=[__name__],
                )()
                LogRecord(
                    f"client_write - Writing telnet option to client {self.uuid}: "
                    f"{msg_obj.line!r}",
                    level="debug",
                    sources=[__name__],
                )()
                self.writer.send_iac(msg_obj.line)
                msg_obj.was_sent = True
                self.data_logger.info("%-12s : %s", "client_write", msg_obj.line)

            count = count + 1
            if count == self.max_lines_to_process:
                await asyncio.sleep(0)
                count = 0

        LogRecord(
            f"client_write - Ending coroutine for {self.uuid}",
            level="debug",
            sources=[__name__],
        )()


async def register_client(connection) -> bool:
    """Register a new client connection.

    This coroutine registers a new client connection by checking if the client is
    banned, logging the registration process, and adding the client to the list of
    active clients.

    Args:
        connection: The `ClientConnection` instance to register.

    Returns:
        True if the client is successfully registered, False if the client is banned.

    Raises:
        None

    """
    if connection.api("plugins.core.clients:client.banned.check")(connection.addr):
        LogRecord(
            f"client_read - {connection.uuid} [{connection.addr}:{connection.port}] "
            "is banned. Closing connection.",
            level="warning",
            sources=[__name__],
        )()
        connection.writer.write("You are banned from this proxy. Goodbye.\n\r")
        with contextlib.suppress(AttributeError):
            await connection.writer.drain()
        connection.connected = False
        return False

    LogRecord(
        f"register_client - Registering client {connection.uuid}",
        level="debug",
        sources=[__name__],
    )()

    connection.api("plugins.core.clients:client.add")(connection)

    LogRecord(
        f"register_client - Registered client {connection.uuid}",
        level="debug",
        sources=[__name__],
    )()

    return True


async def unregister_client(connection) -> None:
    """Unregister a client connection.

    This coroutine unregisters a client connection by logging the unregistration
    process, marking the client as disconnected, and removing the client from the
    list of active clients.

    Args:
        connection: The `ClientConnection` instance to unregister.

    Returns:
        None

    Raises:
        None

    """
    LogRecord(
        f"unregister_client - Unregistering client {connection.uuid}",
        level="debug",
        sources=[__name__],
    )()

    if connection.connected:
        connection.connected = False
    connection.api("plugins.core.clients:client.remove")(connection)

    LogRecord(
        f"unregister_client - Unregistered client {connection.uuid}",
        level="debug",
        sources=[__name__],
    )()


async def client_telnet_handler(
    reader: TelnetReaderUnicode, writer: TelnetWriterUnicode
) -> None:
    """Handle new telnet client connections.

    This coroutine handles new telnet client connections by creating a
    `ClientConnection` instance, registering the client, setting up the client
    connection, and managing the read and write tasks. It ensures proper cleanup
    of tasks and client unregistration when the connection is closed.

    Args:
        reader: The TelnetReaderUnicode instance for reading data.
        writer: The TelnetWriterUnicode instance for writing data.

    Returns:
        None

    Raises:
        None

    """
    client_details: str = writer.get_extra_info("peername")

    addr, port, *rest = client_details
    connection: ClientConnection = ClientConnection(
        addr, port, "telnet", reader, writer
    )
    LogRecord(
        f"Connection established with {addr} : {port} : {rest} : uuid - "
        f"{connection.uuid}",
        level="warning",
        sources=[__name__],
    )()

    if await register_client(connection):
        tasks: list[asyncio.Task] = [
            TaskItem(
                connection.client_read(), name=f"{connection.uuid} telnet read"
            ).create(),
            TaskItem(
                connection.client_write(), name=f"{connection.uuid} telnet write"
            ).create(),
        ]

        if current_task := asyncio.current_task():
            current_task.set_name(f"{connection.uuid} telnet client handler")

        await connection.setup_client()

        # We want to .wait until the first task is completed. "Completed" could be an
        # actual finishing of execution or an exception. If either the reader or writer
        # "completes", we want to ensure we move beyond this point and clean up the
        # tasks associated with this client.
        _, rest = await asyncio.wait(tasks, return_when="FIRST_COMPLETED")

        # Once we reach this point one of our tasks (reader/writer) have completed or
        # failed. Remove client from the registration list and perform connection
        # specific cleanup.
        await unregister_client(connection)

        for task in rest:
            task.cancel()

    # drain and close the writer
    if not writer.is_closing():
        writer.write_eof()
        await writer.drain()
        writer.close()

    # close the reader
    reader.feed_eof()

    await asyncio.sleep(1)
