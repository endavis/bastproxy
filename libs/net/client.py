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
import time
from uuid import uuid4

# Third Party

# Project
from libs.net import telnet
from libs.task_logger import create_task
from libs.api import API
from libs.record import ToClientRecord
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
                Currently used for "softboot" capability
            self.uuid is a uuid.uuid4() for unique session tracking
            self.read_only is a bool to determine if the client is read only
            self.reader is the asyncio.StreamReader for the connection
            self.writer is the asyncio.StreamWriter for the connection

    """
    def __init__(self, addr, port, conn_type, reader, writer, rows=24):
        self.addr: str = addr
        self.port: str = port
        self.rows: int = rows
        self.api = API()
        self.login_attempts: int = 0
        self.conn_type: str = conn_type
        self.state: dict[str, bool] = {'connected': True, 'logged in': False}
        self.uuid = uuid4()
        self.view_only = False
        self.msg_queue = asyncio.Queue()
        self.connected_time = time.localtime()
        self.reader: asyncio.StreamReader = reader
        self.writer: asyncio.StreamWriter = writer
        self.api('plugins.core.clients:client:add')(self)

    async def setup_client(self):
        """
        send telnet options
        send welcome message to client
        ask for password
        """
        if self.api('plugins.core.clients:client:banned:check')(self.addr):
            self.api('libs.io:send:msg')(f"client_read - {self.uuid} [{self.addr}:{self.port}] is banned. Closing connection.", level='info')
            self.writer.write(b'You are banned from this proxy. Goodbye.\n\r')
            try:
                await self.writer.drain()
            except AttributeError:
                # the connection is already closed
                pass
            self.state['connected'] = False
            return

        self.api('libs.io:send:msg')(f"setup_client - Sending telnet options to {self.uuid}", level='debug')
        # We send an IAC+WILL+ECHO to the client so that it won't locally echo the password.
        ToClientRecord([telnet.echo_on()], message_type='COMMAND-TELNET' , clients=[self.uuid], prelogin=True).send('libs.net.client:setup_client')

        # Advertise to the client that we will do features we are capable of.
        features = telnet.advertise_features()
        if features:
            ToClientRecord([telnet.advertise_features()], message_type='COMMAND-TELNET' , clients=[self.uuid], prelogin=True).send('libs.net.client:setup_client')
        self.api('libs.io:send:msg')(f"setup_client - telnet options sent to {self.uuid}", level='debug')

        await self.writer.drain()

        self.api('libs.io:send:msg')(f"setup_client - Sending welcome message to {self.uuid}", level='debug')
        ToClientRecord('Welcome to Bastproxy.', clients=[self.uuid], prelogin=True).send('libs.net.client:setup_client')
        ToClientRecord('Please enter your password.', clients=[self.uuid], prelogin=True).send('libs.net.client:setup_client')
        self.login_attempts += 1
        self.api('libs.io:send:msg')(f"setup_client - welcome message sent to {self.uuid}", )

        await self.writer.drain()

    async def client_read(self) -> None:
        """
            Utilized by the Telnet and SSH client_handlers.

            We want this coroutine to run while the client is connected, so we begin with a while loop
            We first await control back to the loop until we have received some input (or an EOF)
                Mark the connection to disconnected and break out if a disconnect (EOF)
                else we handle the input. Client input packaged into a JSON payload and put into the
                messages_to_game asyncio.Queue()
        """
        self.api('libs.io:send:msg')(f"client_read - Starting coroutine for {self.uuid}", level='debug')

        while self.state['connected']:
            inp: bytes = await self.reader.readline()
            self.api('libs.io:send:msg')(f"client_read - Raw received data in client_read : {inp}", level='debug')
            self.api('libs.io:send:msg')(f"client_read - inp type = {type(inp)}", level='debug')
            logging.getLogger(f"data.{self.uuid}").info(f"{'from_client':<12} : {inp}")

            if not inp:  # This is an EOF.  Hard disconnect.
                self.state['connected'] = False
                return

            if not self.state['logged in']:
                if inp.strip() == 'bastpass':
                    ToClientRecord([telnet.echo_off()], message_type='COMMAND-TELNET' , clients=[self.uuid], prelogin=True).send('libs.net.client:client_read')
                    ToClientRecord(['You are now logged in.'], clients=[self.uuid], prelogin=True).send('libs.net.client:client_read')
                    self.api('plugins.core.clients:client:logged:in')(self.uuid)
                    continue

                elif inp.strip() == 'bastviewpass':
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
                    self.api('libs.io:send:msg')(f"client_read - {self.uuid} [{self.addr}:{self.port}] too many login attempts. Disconnecting.")
                    self.api('plugins.core.clients:client:banned:add')(self.uuid)
                    continue

            else:
                if self.view_only:
                    ToClientRecord(['You are logged in as a view only user.'], clients=[self.uuid]).send('libs.net.client:client_read')
                else:
                    self.api('libs.io:send:execute')(inp, fromclient=True)

        self.api('libs.io:send:msg')(f"Ending client_read coroutine for {self.uuid}", level='debug')

    async def client_write(self) -> None:
        """
            Utilized by the Telnet and SSH client_handlers.

            We want this coroutine to run while the client is connected, so we begin with a while loop
            We await for any messages from the game to this client, then write and drain it.
        """
        self.api('libs.io:send:msg')(f"client_write - Starting client_write coroutine for {self.uuid}", level='debug')
        while self.state['connected']:
            msg_obj: NetworkData = await self.msg_queue.get()
            if msg_obj.is_io:
                if msg_obj.msg:
                    self.api('libs.io:send:msg')(f"client_write - Writing message to client {self.uuid}: {msg_obj.msg}", level='debug')
                    self.api('libs.io:send:msg')(f"client_write - type of msg_obj.msg = {type(msg_obj.msg)}", level='debug')
                    self.writer.write(msg_obj.msg)
                    logging.getLogger(f"data.{self.uuid}").info(f"{'to_client':<12} : {msg_obj.msg}")
                    if msg_obj.is_prompt:
                        self.writer.write(telnet.go_ahead())
                        logging.getLogger(f"data.{self.uuid}").info(f"{'to_client':<12} : {telnet.goahead()}")
                else:
                    self.api('libs.io:send:msg')('client_write - No message to write to client.', level='debug')

            elif msg_obj.is_command_telnet:
                self.api('libs.io:send:msg')(f"client_write - Writing telnet option to client {self.uuid}: {msg_obj.msg}", level='debug')
                self.api('libs.io:send:msg')(f"client_write - type of msg_obj.msg = {type(msg_obj.msg)}", level='debug')
                self.writer.send_iac(msg_obj.msg)
                logging.getLogger(f"data.{self.uuid}").info(f"{'to_client':<12} : {msg_obj.msg}")

            task = create_task(self.writer.drain(), name=f"{self.uuid}.write.drain")
            self.api('libs.io:send:msg')(f"Created task {task.get_name()} for write.drain() in client_write", primary='asyncio', level='debug')

        self.api('libs.io:send:msg')(f"Ending client_write coroutine for {self.uuid}", level='debug')

async def register_client(connection) -> None:
    """
        This function is for things to do before the client is fully connected.
    """
    connection.api('libs.io:send:msg')(f"Registering client {connection.uuid}", primary=__name__, level='debug')

    connection.api('plugins.core.clients:client:add')(connection)

    connection.api('libs.io:send:msg')(f"Registered client {connection.uuid}", primary=__name__, level='debug')


async def unregister_client(connection) -> None:
    """
        Upon client disconnect/quit, we unregister it from the connections dict.
    """
    connection.api('libs.io:send:msg')(f"Unregistering client {connection.uuid}", primary=__name__, level='debug')

    if connection.state['connected']:
        connection.state['connected'] = False
    connection.api('plugins.core.clients:client:remove')(connection)

    connection.api('libs.io:send:msg')(f"Unregistered client {connection.uuid}", primary=__name__, level='debug')


async def client_telnet_handler(reader, writer) -> None:
    """
    This handler is for telnet client connections. Upon a client connection this handler is
    the starting point for creating the tasks necessary to handle the client.
    """
    #log.debug(f"client_telnet_handler - telnet details are: {dir(reader)}")
    client_details: str = writer.get_extra_info('peername')

    addr, port, *rest = client_details
    connection: ClientConnection = ClientConnection(addr, port, 'telnet', reader, writer)
    log.info(f"Connection established with {addr} : {port} : {rest}")

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

