# -*- coding: utf-8 -*-
# Project: bastproxy
# Filename: libs/net/client.py
#
# File Description: Client connection handling.
#
# By: Bast/Jubelo
"""
    Housing the Class(es) and coroutines for accepting and maintaining connections from clients
    via Telnet, Secure Telnet and SSH.

    We do not register to events here, but we do fire events.
"""
# Standard Library
import asyncio
import contextlib
import logging
import datetime
import typing
from uuid import uuid4

# Third Party
from telnetlib3 import TelnetReaderUnicode, TelnetWriterUnicode
if typing.TYPE_CHECKING:
    from telnetlib3 import TelnetServer

# Project
from libs.net import telnet
from libs.asynch import TaskItem
from libs.api import API
from libs.records import ToClientData, LogRecord, ProcessDataToMud, NetworkDataLine, NetworkData, SendDataDirectlyToClient


class ClientConnection:
    """
        Each connection when created in async handle_client will instantiate this class.

        Instance variables:
            self.addr is the IP address portion of the client
            self.port is the port portion of the client
            self.conn_type is the type of client connection
            self.rows is the number of rows the client requested
            self.login_attempts is the number of login attempts
                close connection and ban IP for 10 minutes on 3 failed attempts
            self.state is the current state of the client connection
            self.uuid is a uuid.uuid4() converted to hex for unique session tracking
            self.view_only is a bool to determine if the client is view only
            self.reader is the telnetlib3.TelnetReaderUnicode for the connection
            self.writer is the telnetlib3.TelnetWriterUnicode for the connection

    """
    def __init__(self, addr, port, conn_type, reader, writer, rows=24):
        self.uuid = uuid4().hex
        self.addr: str = addr
        self.port: str = port
        self.rows: int = rows
        self.api = API(owner_id=f"{__name__}:{self.uuid}")
        self.login_attempts: int = 0
        self.conn_type: str = conn_type
        self.connected: bool = True
        self.state: dict[str, bool] = {'logged in': False}
        self.view_only = False
        self.send_queue: asyncio.Queue[NetworkDataLine] = asyncio.Queue()
        self.connected_time =  datetime.datetime.now(datetime.timezone.utc)
        self.reader: TelnetReaderUnicode = reader
        self.writer: TelnetWriterUnicode = writer
        self.telnet_server: 'TelnetServer | None' = self.writer.protocol
        self.data_logger = logging.getLogger(f"data.client.{self.uuid}")
        self.max_lines_to_process = 15

    @property
    def connected_length(self) -> str:
        return self.api('plugins.core.utils:convert.timedelta.to.string')(
                 self.connected_time,
                 datetime.datetime.now(datetime.timezone.utc))

    def send_to(self, data: NetworkDataLine) -> None:
        """
        add data to the queue
        """
        if not self.connected:
            LogRecord(f"send_to - {self.uuid} [{self.addr}:{self.port}] is not connected. Cannot send",
                      level='debug',
                      sources=[__name__])()
            return
        loop = asyncio.get_event_loop()
        if not isinstance(data, NetworkDataLine):
            LogRecord(f"client: send_to - {self.uuid} got a type that is not NetworkDataLine : {type(data)}",
                      level='error', stack_info=True,
                      sources=[__name__])()
        else:
            loop.call_soon_threadsafe(self.send_queue.put_nowait, data)

    async def setup_client(self) -> None:
        """
        send telnet options
        send welcome message to client
        ask for password
        """
        LogRecord(f"setup_client - Sending echo on to {self.uuid}",
                  level='debug',
                  sources=[__name__])()
        # We send an IAC+WILL+ECHO to the client so that it won't locally echo the password.
        networkdata = NetworkData([NetworkDataLine(telnet.echo_on(), line_type="COMMAND-TELNET", prelogin=True)],
                                  owner_id=f"client:{self.uuid}")
        SendDataDirectlyToClient(networkdata,
                                 clients=[self.uuid])()

        if features := telnet.advertise_features():
            networkdata = NetworkData([NetworkDataLine(features, line_type="COMMAND-TELNET", prelogin=True)],
                                          owner_id=f"client:{self.uuid}")
            LogRecord(f"setup_client - Sending telnet features to {self.uuid}",
                      level='debug',
                      sources=[__name__])()
            SendDataDirectlyToClient(networkdata,
                           clients=[self.uuid])()
            LogRecord(f"setup_client - telnet features sent to {self.uuid}",
                      level='debug',
                      sources=[__name__])()

        await self.writer.drain()

        LogRecord(f"setup_client - Sending welcome message to {self.uuid}",
                  level='debug',
                  sources=[__name__])()
        networkdata = NetworkData([NetworkDataLine('Welcome to Bastproxy.', prelogin=True)],
                                  owner_id=f"client:{self.uuid}")
        networkdata.append(NetworkDataLine('Please enter your password.', prelogin=True))
        SendDataDirectlyToClient(networkdata,
                       clients=[self.uuid])()
        self.login_attempts += 1
        LogRecord(f"setup_client - welcome message sent to {self.uuid}",
                  level='debug',
                  sources=[__name__])()

        await self.writer.drain()

    async def client_read(self) -> None:
        """
            Utilized by the Telnet client_handler.

            We want this coroutine to run while the client is connected, so we begin with a while loop
        """
        LogRecord(f"client_read - Starting coroutine for {self.uuid}",
                  level='debug',
                  sources=[__name__])()

        while self.connected:
            try:
                inp: str = await self.reader.readline()
            except BrokenPipeError:
                self.connected = False
                continue
            LogRecord(f"client_read - Raw received data in client_read : {inp}",
                      level='debug',
                      sources=[__name__])()
            LogRecord(f"client_read - inp type = {type(inp)}",
                      level='debug',
                      sources=[__name__])()
            self.data_logger.info(f"{'client_read':<12} : {inp}")

            if not inp:  # This is an EOF.  Hard disconnect.
                self.connected = False
                return

            if not self.state['logged in']:
                dpw = self.api('plugins.core.proxy:ssc.proxypw')()
                vpw = self.api('plugins.core.proxy:ssc.proxypwview')()
                if inp.strip() == dpw:
                    networkdata = NetworkData([NetworkDataLine(telnet.echo_off(), line_type="COMMAND-TELNET", prelogin=True)],
                                              owner_id=f"client:{self.uuid}")
                    networkdata.append(NetworkDataLine('You are now logged in.', prelogin=True))
                    SendDataDirectlyToClient(networkdata,
                                   clients=[self.uuid])()
                    self.api('plugins.core.clients:client.logged.in')(self.uuid)
                elif inp.strip() == vpw:
                    networkdata = NetworkData([NetworkDataLine(telnet.echo_off(), line_type="COMMAND-TELNET", prelogin=True)],
                                              owner_id=f"client:{self.uuid}")
                    networkdata.append(NetworkDataLine('You are now logged in as view only user.', prelogin=True))
                    SendDataDirectlyToClient(networkdata,
                                   clients=[self.uuid])()
                    self.api('plugins.core.clients:client.logged.in.view.only')(self.uuid)

                elif self.login_attempts < 3:
                    self.login_attempts = self.login_attempts + 1
                    networkdata = NetworkData([NetworkDataLine('Invalid password. Please try again.', prelogin=True)],
                                              owner_id=f"client:{self.uuid}")
                    SendDataDirectlyToClient(networkdata,
                                   clients=[self.uuid])()

                else:
                    networkdata = NetworkData([NetworkDataLine('Too many login attempts. Goodbye.', prelogin=True)],
                                              owner_id=f"client:{self.uuid}")
                    SendDataDirectlyToClient(networkdata,
                                   clients=[self.uuid])()
                    LogRecord(f"client_read - {self.uuid} [{self.addr}:{self.port}] too many login attempts. Disconnecting.",
                              level='warning',
                              sources=[__name__])()
                    self.api('plugins.core.clients:client.banned.add')(self.uuid)
                continue

            elif self.view_only:
                networkdata = NetworkData([NetworkDataLine('As a view only user, you cannot enter commands')],
                                          owner_id=f"client:{self.uuid}")
                SendDataDirectlyToClient(networkdata,
                                clients=[self.uuid])()
            else:
                # this is where we start processing data
                ProcessDataToMud(NetworkData(NetworkDataLine(inp.strip(), originated='client'),
                                                  owner_id=f"client:{self.uuid}"),
                                        client_id=self.uuid)()

        LogRecord(f"client_read - Ending coroutine for {self.uuid}",
                  level='debug',
                  sources=[__name__])()

    async def client_write(self) -> None:
        """
            Utilized by the Telnet and SSH client_handlers.

            We want this coroutine to run while the client is connected, so we begin with a while loop
            We await for any messages from the game to this client, then write and drain it.
        """
        LogRecord(f"client_write - Starting coroutine for {self.uuid}",
                  level='debug',
                  sources=[__name__])()

        count = 0
        while self.connected and not self.writer.connection_closed:
            msg_obj: NetworkDataLine = await self.send_queue.get()
            if msg_obj.is_io:
                if msg_obj.line:
                    LogRecord(f"client_write - Writing message to client {self.uuid}: {msg_obj.line}",
                            level='debug',
                            sources=[__name__])()
                    LogRecord(f"client_write - type of msg_obj.msg = {type(msg_obj.line)}",
                            level='debug',
                            sources=[__name__])()
                    self.writer.write(msg_obj.line)
                    msg_obj.was_sent = True
                    self.data_logger.info(f"{'client_write':<12} : {msg_obj.line}")
                else:
                    LogRecord(
                        "client_write - No message to write to client.",
                        level='debug',
                        sources=[__name__],
                    )()
                if msg_obj.is_prompt:
                    self.writer.write(telnet.go_ahead())
                    self.data_logger.info(f"{'client_write':<12} : {telnet.go_ahead()}")
            elif msg_obj.is_command_telnet:
                LogRecord(f"client_write - type of msg_obj.msg = {type(msg_obj.line)}",
                        level='debug',
                        sources=[__name__])()
                LogRecord(f"client_write - Writing telnet option to client {self.uuid}: {repr(msg_obj.line)}",
                            level='debug',
                            sources=[__name__])()
                self.writer.send_iac(msg_obj.line)
                msg_obj.was_sent = True
                self.data_logger.info(f"{'client_write':<12} : {msg_obj.line}")

            count = count + 1
            if count == self.max_lines_to_process:
                await asyncio.sleep(0)
                count = 0

        LogRecord(f"client_write - Ending coroutine for {self.uuid}",
                  level='debug',
                  sources=[__name__])()

async def register_client(connection) -> bool:
    """
        This function is for things to do before the client is fully connected.
    """
    if connection.api('plugins.core.clients:client.banned.check')(connection.addr):
        LogRecord(f"client_read - {connection.uuid} [{connection.addr}:{connection.port}] is banned. Closing connection.",
                    level='warning',
                    sources=[__name__])()
        connection.writer.write('You are banned from this proxy. Goodbye.\n\r')
        with contextlib.suppress(AttributeError):
            await connection.writer.drain()
        connection.connected = False
        return False

    LogRecord(f"register_client - Registering client {connection.uuid}",
              level='debug',
              sources=[__name__])()

    connection.api('plugins.core.clients:client.add')(connection)

    LogRecord(f"register_client - Registered client {connection.uuid}",
              level='debug',
              sources=[__name__])()

    return True

async def unregister_client(connection) -> None:
    """
        Upon client disconnect/quit, we unregister it from the connections dict.
    """
    LogRecord(f"unregister_client - Unregistering client {connection.uuid}",
              level='debug',
              sources=[__name__])()

    if connection.connected:
        connection.connected = False
    connection.api('plugins.core.clients:client.remove')(connection)

    LogRecord(f"unregister_client - Unregistered client {connection.uuid}",
              level='debug',
              sources=[__name__])()


async def client_telnet_handler(reader: TelnetReaderUnicode, writer: TelnetWriterUnicode) -> None:
    """
    This handler is for telnet client connections. Upon a client connection this handler is
    the starting point for creating the tasks necessary to handle the client.
    """
    client_details: str = writer.get_extra_info('peername')

    addr, port, *rest = client_details
    connection: ClientConnection = ClientConnection(addr, port, 'telnet', reader, writer)
    LogRecord(f"Connection established with {addr} : {port} : {rest} : uuid - {connection.uuid}",
              level='warning',
              sources=[__name__])()

    if await register_client(connection):

        tasks: list[asyncio.Task] = [
            TaskItem(connection.client_read(),
                                name=f"{connection.uuid} telnet read").create(),
            TaskItem(connection.client_write(),
                                name=f"{connection.uuid} telnet write").create(),
        ]

        if current_task := asyncio.current_task():
            current_task.set_name(f"{connection.uuid} telnet client handler")

        await connection.setup_client()

        # We want to .wait until the first task is completed.  "Completed" could be an actual finishing
        # of execution or an exception.  If either the reader or writer "completes", we want to ensure
        # we move beyond this point and cleanup the tasks associated with this client.
        _, rest = await asyncio.wait(tasks, return_when='FIRST_COMPLETED')

        # Once we reach this point one of our tasks (reader/writer) have completed or failed.
        # Remove client from the registration list and perform connection specific cleanup.
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

