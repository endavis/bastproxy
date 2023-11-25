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
from uuid import uuid4

# Third Party
from telnetlib3 import TelnetReaderUnicode, TelnetWriterUnicode

# Project
from libs.net import telnet
from libs.asynch import TaskItem
from libs.api import API
from libs.records import ToClientRecord, LogRecord, ToMudRecord
from libs.net.networkdata import NetworkData

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
        self.send_queue: asyncio.Queue[NetworkData] = asyncio.Queue()
        self.connected_time =  datetime.datetime.now(datetime.timezone.utc)
        self.reader: TelnetReaderUnicode = reader
        self.writer: TelnetWriterUnicode = writer

    @property
    def connected_length(self) -> str:
        return self.api('plugins.core.utils:convert.timedelta.to.string')(
                 self.connected_time,
                 datetime.datetime.now(datetime.timezone.utc))

    def send_to(self, data: ToClientRecord) -> None:
        """
        add data to the queue
        """
        if not self.connected:
            LogRecord(f"send_to - {self.uuid} [{self.addr}:{self.port}] is not connected. Cannot send",
                      level='debug',
                      sources=[__name__])()
            return
        loop = asyncio.get_event_loop()
        if data.is_io:
            message = NetworkData(data.message_type,
                                  message=''.join(data),
                                  client_uuid=self.uuid)
            loop.call_soon_threadsafe(self.send_queue.put_nowait, message)
        else:
            for i in data:
                message = NetworkData(data.message_type,
                                      message=i,
                                      client_uuid=self.uuid)
                loop.call_soon_threadsafe(self.send_queue.put_nowait, message)

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
        ToClientRecord([telnet.echo_on()],
                       message_type='COMMAND-TELNET' ,
                       clients=[self.uuid],
                       prelogin=True)('libs.net.client:setup_client')

        if features := telnet.advertise_features():
            LogRecord(f"setup_client - Sending telnet features to {self.uuid}",
                      level='debug',
                      sources=[__name__])()
            ToClientRecord([features],
                           message_type='COMMAND-TELNET' ,
                           clients=[self.uuid],
                           prelogin=True)('libs.net.client:setup_client')
            LogRecord(f"setup_client - telnet features sent to {self.uuid}",
                      level='debug',
                      sources=[__name__])()

        await self.writer.drain()

        LogRecord(f"setup_client - Sending welcome message to {self.uuid}",
                  level='debug',
                  sources=[__name__])()
        ToClientRecord('Welcome to Bastproxy.',
                       clients=[self.uuid],
                       prelogin=True)('libs.net.client:setup_client')
        ToClientRecord('Please enter your password.',
                       clients=[self.uuid],
                       prelogin=True)('libs.net.client:setup_client')
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
            logging.getLogger(f"data.{self.uuid}").info(f"{'from_client':<12} : {inp}")

            if not inp:  # This is an EOF.  Hard disconnect.
                self.connected = False
                return

            if not self.state['logged in']:
                dpw = self.api('plugins.core.proxy:ssc.proxypw')()
                vpw = self.api('plugins.core.proxy:ssc.proxypwview')()
                if inp.strip() == dpw:
                    ToClientRecord([telnet.echo_off()],
                                   message_type='COMMAND-TELNET' ,
                                   clients=[self.uuid],
                                   prelogin=True)('libs.net.client:client_read')
                    ToClientRecord(['You are now logged in.'],
                                   clients=[self.uuid],
                                   prelogin=True)('libs.net.client:client_read')
                    self.api('plugins.core.clients:client.logged.in')(self.uuid)
                elif inp.strip() == vpw:
                    ToClientRecord([telnet.echo_off()], message_type='COMMAND-TELNET' ,
                                   clients=[self.uuid],
                                   prelogin=True)('libs.net.client:client_read')
                    ToClientRecord(['You are now logged in as view only user.'],
                                   clients=[self.uuid],
                                   prelogin=True)('libs.net.client:client_read')
                    self.api('plugins.core.clients:client.logged.in.view.only')(self.uuid)
                    continue

                elif self.login_attempts < 3:
                    self.login_attempts = self.login_attempts + 1
                    ToClientRecord(['Invalid password. Please try again.'],
                                   clients=[self.uuid],
                                   prelogin=True)('libs.net.client:client_read')
                    continue

                else:
                    ToClientRecord(['Too many login attempts. Goodbye.'],
                                   clients=[self.uuid],
                                   prelogin=True)('libs.net.client:client_read')
                    LogRecord(f"client_read - {self.uuid} [{self.addr}:{self.port}] too many login attempts. Disconnecting.",
                              level='warning',
                              sources=[__name__])()
                    self.api('plugins.core.clients:client.banned.add')(self.uuid)
                    continue

            elif self.view_only:
                ToClientRecord(['You are logged in as a view only user.'],
                                clients=[self.uuid])('libs.net.client:client_read')
            else:
                # this is where we start with ToMudRecord
                ToMudRecord(inp,
                            internal=False,
                            client_id=self.uuid)('libs.net.client:client_read')

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
        while self.connected:
            msg_obj: NetworkData = await self.send_queue.get()
            if msg_obj.is_io:
                if msg_obj.msg:
                    LogRecord(f"client_write - Writing message to client {self.uuid}: {msg_obj.msg}",
                              level='debug',
                              sources=[__name__])()
                    LogRecord(f"client_write - type of msg_obj.msg = {type(msg_obj.msg)}",
                              level='debug',
                              sources=[__name__])()
                    self.writer.write(msg_obj.msg)
                    logging.getLogger(f"data.{self.uuid}").info(f"{'to_client':<12} : {msg_obj.msg}")
                    if msg_obj.is_prompt:
                        self.writer.write(telnet.go_ahead())
                        logging.getLogger(f"data.{self.uuid}").info(f"{'to_client':<12} : {telnet.go_ahead()}")
                else:
                    LogRecord(
                        "client_write - No message to write to client.",
                        level='debug',
                        sources=[__name__],
                    )()

            elif msg_obj.is_command_telnet:
                LogRecord(f"client_write - Writing telnet option to client {self.uuid}: {msg_obj.msg}",
                          level='debug',
                          sources=[__name__])()
                LogRecord(f"client_write - type of msg_obj.msg = {type(msg_obj.msg)}",
                          level='debug',
                          sources=[__name__])()
                self.writer.send_iac(msg_obj.msg)
                logging.getLogger(f"data.{self.uuid}").info(f"{'to_client':<12} : {msg_obj.msg}")

            # ensure the client is connected before we drain the writer
            # this can happen if the client disconnects while a task is waiting to write
            if self.connected:
                self.api('libs.asynch:task.add')(self.writer.drain, name=f"{self.uuid}.write.drain")

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


async def client_telnet_handler(reader, writer) -> None:
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

    # Need to work on better telnet support for regular old telnet clients.
    # Everything so far works great in Mudlet.  Just saying....

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

    with contextlib.suppress(AttributeError):
        #print(f"Closing writer with {addr} : {port} : {rest} : uuid - {connection.uuid}")
        writer.write_eof()
        await writer.drain()
        writer.close()
        #print(f"Closing reader with {addr} : {port} : {rest} : uuid - {connection.uuid}")
        reader.write_eof()
        await reader.drain()
        reader.close()

    await asyncio.sleep(1)

