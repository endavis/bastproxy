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
import logging
import datetime
from uuid import uuid4

# Third Party

# Project
from libs.net import telnet
from libs.asynch.task_logger import create_task
from libs.api import API
from libs.records import ToClientRecord, LogRecord
from libs.net.networkdata import NetworkData

log = logging.getLogger(__name__)

class ClientConnection:
    """
        Each connection when created in async handle_client will instantiate this class.

        Instance variables:
            self.addr is the IP address portion of the client
            self.port is the port portion of the client
            self.conn_type is the type of client connection
            self.rows is the number of rows the client requested
            self.login_attempts is the number of login attempts
                close connection on 3 failed attempts
            self.state is the current state of the client connection
            self.uuid is a uuid.uuid4() converted to hex for unique session tracking
            self.view_only is a bool to determine if the client is view only
            self.reader is the asyncio.StreamReader for the connection
            self.writer is the asyncio.StreamWriter for the connection

    """
    def __init__(self, addr, port, conn_type, reader, writer, rows=24):
        self.uuid = uuid4().hex
        self.addr: str = addr
        self.port: str = port
        self.rows: int = rows
        self.api = API(parent_id=f"{__name__}:{self.uuid}")
        self.login_attempts: int = 0
        self.conn_type: str = conn_type
        self.state: dict[str, bool] = {'connected': True, 'logged in': False}
        self.view_only = False
        self.msg_queue = asyncio.Queue()
        self.connected_time =  datetime.datetime.now(datetime.timezone.utc)
        self.reader: asyncio.StreamReader = reader
        self.writer: asyncio.StreamWriter = writer

    async def setup_client(self):
        """
        send telnet options
        send welcome message to client
        ask for password
        """
        if self.api('plugins.core.clients:client:banned:check')(self.addr):
            LogRecord(f"client_read - {self.uuid} [{self.addr}:{self.port}] is banned. Closing connection.", level='warning', sources=[__name__]).send()
            self.writer.write('You are banned from this proxy. Goodbye.\n\r')
            try:
                await self.writer.drain()
            except AttributeError:
                # the connection is already closed
                pass
            self.state['connected'] = False
            return

        LogRecord(f"setup_client - Sending echo on to {self.uuid}", level='debug', sources=[__name__]).send()
        # We send an IAC+WILL+ECHO to the client so that it won't locally echo the password.
        ToClientRecord([telnet.echo_on()], message_type='COMMAND-TELNET' , clients=[self.uuid], prelogin=True).send('libs.net.client:setup_client')

        # Advertise to the client that we will do features we are capable of.
        features = telnet.advertise_features()
        if features:
            LogRecord(f"setup_client - Sending telnet features to {self.uuid}", level='debug', sources=[__name__]).send()
            ToClientRecord([telnet.advertise_features()], message_type='COMMAND-TELNET' , clients=[self.uuid], prelogin=True).send('libs.net.client:setup_client')
            LogRecord(f"setup_client - telnet features sent to {self.uuid}", level='debug', sources=[__name__]).send()

        await self.writer.drain()

        LogRecord(f"setup_client - Sending welcome message to {self.uuid}", level='debug', sources=[__name__]).send()
        ToClientRecord('Welcome to Bastproxy.', clients=[self.uuid], prelogin=True).send('libs.net.client:setup_client')
        ToClientRecord('Please enter your password.', clients=[self.uuid], prelogin=True).send('libs.net.client:setup_client')
        self.login_attempts += 1
        LogRecord(f"setup_client - welcome message sent to {self.uuid}", level='debug', sources=[__name__]).send()

        await self.writer.drain()

    async def client_read(self) -> None:
        """
            Utilized by the Telnet client_handler.

            We want this coroutine to run while the client is connected, so we begin with a while loop
        """
        LogRecord(f"client_read - Starting coroutine for {self.uuid}", level='debug', sources=[__name__]).send()

        while self.state['connected']:
            inp: bytes = await self.reader.readline()
            LogRecord(f"client_read - Raw received data in client_read : {inp}", level='debug', sources=[__name__]).send()
            LogRecord(f"client_read - inp type = {type(inp)}", level='debug', sources=[__name__]).send()
            logging.getLogger(f"data.{self.uuid}").info(f"{'from_client':<12} : {inp}")

            if not inp:  # This is an EOF.  Hard disconnect.
                self.state['connected'] = False
                return

            if not self.state['logged in']:
                dpw = self.api('plugins.core.proxy:ssc:proxypw')()
                vpw = self.api('plugins.core.proxy:ssc:proxypwview')()
                if inp.strip() == dpw:
                    ToClientRecord([telnet.echo_off()], message_type='COMMAND-TELNET' , clients=[self.uuid], prelogin=True).send('libs.net.client:client_read')
                    ToClientRecord(['You are now logged in.'], clients=[self.uuid], prelogin=True).send('libs.net.client:client_read')
                    self.api('plugins.core.clients:client:logged:in')(self.uuid)
                    continue

                elif inp.strip() == vpw:
                    ToClientRecord([telnet.echo_off()], message_type='COMMAND-TELNET' , clients=[self.uuid], prelogin=True).send('libs.net.client:client_read')
                    ToClientRecord(['You are now logged in as view only user.'], clients=[self.uuid], prelogin=True).send('libs.net.client:client_read')
                    self.api('plugins.core.clients:client:logged:in:view:only')(self.uuid)
                    continue

                elif self.login_attempts < 3:
                    self.login_attempts = self.login_attempts + 1
                    ToClientRecord(['Invalid password. Please try again.'], clients=[self.uuid], prelogin=True).send('libs.net.client:client_read')
                    continue

                else:
                    ToClientRecord(['Too many login attempts. Goodbye.'], clients=[self.uuid], prelogin=True).send('libs.net.client:client_read')
                    LogRecord(f"client_read - {self.uuid} [{self.addr}:{self.port}] too many login attempts. Disconnecting.",
                              level='warning', sources=[__name__]).send()
                    self.api('plugins.core.clients:client:banned:add')(self.uuid)
                    continue

            else:
                if self.view_only:
                    ToClientRecord(['You are logged in as a view only user.'], clients=[self.uuid]).send('libs.net.client:client_read')
                else:
                    self.api('libs.io:send:execute')(inp, fromclient=True)

        LogRecord(f"client_read - Ending coroutine for {self.uuid}", level='debug', sources=[__name__]).send()

    async def client_write(self) -> None:
        """
            Utilized by the Telnet and SSH client_handlers.

            We want this coroutine to run while the client is connected, so we begin with a while loop
            We await for any messages from the game to this client, then write and drain it.
        """
        LogRecord(f"client_write - Starting coroutine for {self.uuid}", level='debug', sources=[__name__]).send()
        while self.state['connected']:
            msg_obj: NetworkData = await self.msg_queue.get()
            if msg_obj.is_io:
                if msg_obj.msg:
                    LogRecord(f"client_write - Writing message to client {self.uuid}: {msg_obj.msg}", level='debug', sources=[__name__]).send()
                    LogRecord(f"client_write - type of msg_obj.msg = {type(msg_obj.msg)}", level='debug', sources=[__name__]).send()
                    self.writer.write(msg_obj.msg)
                    logging.getLogger(f"data.{self.uuid}").info(f"{'to_client':<12} : {msg_obj.msg}")
                    if msg_obj.is_prompt:
                        self.writer.write(telnet.go_ahead())
                        logging.getLogger(f"data.{self.uuid}").info(f"{'to_client':<12} : {telnet.goahead()}")
                else:
                    LogRecord(f"client_write - No message to write to client.", level='debug', sources=[__name__]).send()

            elif msg_obj.is_command_telnet:
                LogRecord(f"client_write - Writing telnet option to client {self.uuid}: {msg_obj.msg}", level='debug', sources=[__name__]).send()
                LogRecord(f"client_write - type of msg_obj.msg = {type(msg_obj.msg)}", level='debug', sources=[__name__]).send()
                self.writer.send_iac(msg_obj.msg)
                logging.getLogger(f"data.{self.uuid}").info(f"{'to_client':<12} : {msg_obj.msg}")

            self.api('libs.asynch:task:add')(self.writer.drain, name=f"{self.uuid}.write.drain")

        LogRecord(f"client_write - Ending coroutine for {self.uuid}", level='debug', sources=[__name__]).send()

async def register_client(connection) -> None:
    """
        This function is for things to do before the client is fully connected.
    """
    LogRecord(f"register_client - Registering client {connection.uuid}", level='debug', sources=[__name__]).send()

    connection.api('plugins.core.clients:client:add')(connection)

    LogRecord(f"register_client - Registered client {connection.uuid}", level='debug', sources=[__name__]).send()


async def unregister_client(connection) -> None:
    """
        Upon client disconnect/quit, we unregister it from the connections dict.
    """
    LogRecord(f"unregister_client - Unregistering client {connection.uuid}", level='debug', sources=[__name__]).send()

    if connection.state['connected']:
        connection.state['connected'] = False
    connection.api('plugins.core.clients:client:remove')(connection)

    LogRecord(f"unregister_client - Unregistered client {connection.uuid}", level='debug', sources=[__name__]).send()


async def client_telnet_handler(reader, writer) -> None:
    """
    This handler is for telnet client connections. Upon a client connection this handler is
    the starting point for creating the tasks necessary to handle the client.
    """
    client_details: str = writer.get_extra_info('peername')

    addr, port, *rest = client_details
    connection: ClientConnection = ClientConnection(addr, port, 'telnet', reader, writer)
    LogRecord(f"Connection established with {addr} : {port} : {rest} : uuid - {connection.uuid}", level='warning', sources=[__name__]).send()

    # Need to work on better telnet support for regular old telnet clients.
    # Everything so far works great in Mudlet.  Just saying....

    await register_client(connection)

    tasks: list[asyncio.Task] = [
        create_task(connection.client_read(),
                            name=f"{connection.uuid} telnet read"),
        create_task(connection.client_write(),
                            name=f"{connection.uuid} telnet write"),
    ]

    asyncio.current_task().set_name(f"{connection.uuid} telnet client handler")

    await connection.setup_client()

    # We want to .wait until the first task is completed.  "Completed" could be an actual finishing
    # of execution or an exception.  If either the reader or writer "completes", we want to ensure
    # we move beyond this point and cleanup the tasks associated with this client.
    _, rest = await asyncio.wait(tasks, return_when='FIRST_COMPLETED')

    # Once we reach this point one of our tasks (reader/writer) have completed or failed.
    # Remove client from the registration list and perform connection specific cleanup.
    await unregister_client(connection)

    try:
        writer.write_eof()
        await writer.drain()
        writer.close()
    except AttributeError:
        # The transport was already closed
        pass

    for task in rest:
        task.cancel()

    await asyncio.sleep(1)

