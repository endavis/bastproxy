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
from uuid import uuid4

# Third Party

# Project
from libs.net import telnet
from libs.task_logger import create_task
import libs.api
from libs.net.networkdata import NetworkData

log = logging.getLogger(__name__)

connections = {}

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
            self.uuid is a str(uuid.uuid4()) for unique session tracking
            self.read_only is a bool to determine if the client is read only
            self.reader is the asyncio.StreamReader for the connection
            self.writer is the asyncio.StreamWriter for the connection

    """
    def __init__(self, addr, port, conn_type, reader, writer, rows=24):
        self.addr: str = addr
        self.port: str = port
        self.rows: int = rows
        self.api = libs.api.API()
        self.login_attempts: int = 0
        self.conn_type: str = conn_type
        self.state: dict[str, bool] = {'connected': True, 'logged in': False}
        self.uuid: str = str(uuid4())
        self.view_only = False
        self.msg_queue = asyncio.Queue()
        self.reader: asyncio.StreamReader = reader
        self.writer: asyncio.StreamWriter = writer

    async def setup_client(self):
        """
        send telnet options
        send welcome message to client
        ask for password
        """
        if self.api('core.clients:client:banned:check')(self.addr):
            log.info(f"client_read - {self.uuid} [{self.addr}:{self.port}] is banned. Closing connection.")
            self.writer.write(b'You are banned from this proxy. Goodbye.\n\r')
            try:
                await self.writer.drain()
            except AttributeError:
                # the connection is already closed
                pass
            self.state['connected'] = False
            return

        log.debug(f"setup_client - Sending telnet options to {self.uuid}")
        # We send an IAC+WONT+ECHO to the client so that it locally echo's it's own input.
        self.api('libs.io:send:client')([telnet.echo_on()], msg_type='COMMAND-TELNET', client_uuid=self.uuid)

        # Advertise to the client that we will do features we are capable of.
        features = telnet.advertise_features()
        if features:
            self.api('libs.io:send:client')([telnet.advertise_features()], msg_type='COMMAND-TELNET', client_uuid=self.uuid)
        log.debug(f"setup_client - telnet options sent to {self.uuid}")

        await self.writer.drain()

        log.debug(f"setup_client - Sending welcome message to {self.uuid}")
        self.api('libs.io:send:client')(['Welcome to Bastproxy.'], internal=True, client_uuid=self.uuid)
        self.api('libs.io:send:client')(['Please enter your password.'], internal=True, client_uuid=self.uuid)
        self.login_attempts += 1
        log.debug(f"setup_client - welcome message sent to {self.uuid}")

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
        log.debug(f"client_read - Starting coroutine for {self.uuid}")

        while self.state['connected']:
            inp: bytes = await self.reader.readline()
            log.debug(f"client_read - Raw received data in client_read : {inp}")
            log.debug(f"client_read - inp type = {type(inp)}")
            logging.getLogger(f"data.{self.uuid}").info(f"{'from_client':<12} : {inp}")

            if not inp:  # This is an EOF.  Hard disconnect.
                self.state['connected'] = False
                return

            if not self.state['logged in']:
                if inp.strip() == 'bastpass':
                    self.state['logged in'] = True
                    # EVENT: client_logged_in
                    msg = 'You are now logged in.'
                    self.api('libs.io:send:client')([telnet.echo_off()], msg_type='COMMAND-TELNET', client_uuid=self.uuid)
                    self.api('libs.io:send:client')([msg], internal=True, client_uuid=self.uuid)
                    log.info(f"client_read - {self.uuid} [{self.addr}:{self.port}] logged in.")
                    self.api('core.events:raise:event')('ev_libs.net.client_client_connected', {'client':self},
                                              calledfrom="client")
                    continue

                elif inp.strip() == 'bastviewpass':
                    self.state['logged in'] = True
                    self.view_only = True
                    # EVENT: view_client_logged_in
                    msg = 'You are now logged in as view only user.'
                    self.api('libs.io:send:client')([telnet.echo_off()], msg_type='COMMAND-TELNET', client_uuid=self.uuid)
                    self.api('libs.io:send:client')([msg], internal=True, client_uuid=self.uuid)
                    log.info(f"client_read - {self.uuid} [{self.addr}:{self.port}] logged in as view only.")
                    self.api('core.events:raise:event')('ev_libs.net.client_client_connected_view',
                                              {'client':self}, calledfrom="client")
                    continue

                elif self.login_attempts < 3:
                    msg = 'Invalid password. Please try again.'
                    self.login_attempts = self.login_attempts + 1
                    self.api('libs.io:send:client')([msg], internal=True, client_uuid=self.uuid)
                    continue

                else:
                    self.api('libs.io:send:client')(['Too many login attempts. Goodbye.'], internal=True, client_uuid=self.uuid)
                    self.api('libs.io:send:client')(['You have been BANNED for 10 minutes'], internal=True, client_uuid=self.uuid)
                    await asyncio.sleep(1)
                    log.info(f"client_read - {self.uuid} [{self.addr}:{self.port}] too many login attempts. Disconnecting.")
                    self.api('core.clients:client:banned:add')(self)
                    self.state['connected'] = False

            else:
                if self.view_only:
                    self.api('libs.io:send:client')(['You are logged in as a view only user.'], internal=True, client_uuid=self.uuid)
                else:
                    self.api('libs.io:send:execute')(inp, fromclient=True)

        self.api('core.events:raise:event')('ev_libs.net.client_client_disconnected',
                                {'client':self}, calledfrom="client")

        log.debug(f"Ending client_read coroutine for {self.uuid}")

    async def client_write(self) -> None:
        """
            Utilized by the Telnet and SSH client_handlers.

            We want this coroutine to run while the client is connected, so we begin with a while loop
            We await for any messages from the game to this client, then write and drain it.
        """
        log.debug(f"client_write - Starting client_write coroutine for {self.uuid}")
        while self.state['connected']:
            msg_obj: NetworkData = await self.msg_queue.get()
            if msg_obj.is_io:
                if msg_obj.msg:
                    log.debug(f"client_write - Writing message to client {self.uuid}: {msg_obj.msg}")
                    log.debug(f"client_write - type of msg_obj.msg = {type(msg_obj.msg)}")
                    self.writer.write(msg_obj.msg)
                    logging.getLogger(f"data.{self.uuid}").info(f"{'to_client':<12} : {msg_obj.msg}")
                    if msg_obj.is_prompt:
                        self.writer.write(telnet.go_ahead())
                        logging.getLogger(f"data.{self.uuid}").info(f"{'to_client':<12} : {telnet.goahead()}")
                else:
                    log.debug('client_write - No message to write to client.')

            elif msg_obj.is_command_telnet:
                log.debug(f"client_write - Writing telnet option to client {self.uuid}: {msg_obj.msg}")
                log.debug(f"client_write - type of msg_obj.msg = {type(msg_obj.msg)}")
                self.writer.send_iac(msg_obj.msg)
                logging.getLogger(f"data.{self.uuid}").info(f"{'to_client':<12} : {msg_obj.msg}")

            task = create_task(self.writer.drain(), name=f"{self.uuid}.write.drain")
            logging.getLogger("asyncio").debug(f"Created task {task.get_name()} for write.drain() in client_write")

        log.debug(f"Ending client_write coroutine for {self.uuid}")

async def register_client(connection) -> None:
    """
        Upon a new client connection, we register it to the connections dict.
    """
    log.debug(f"Registering client {connection.uuid}")
    connections[connection.uuid] = connection

    log.debug(f"Registered client {connection.uuid}")


async def unregister_client(connection) -> None:
    """
        Upon client disconnect/quit, we unregister it from the connections dict.
    """
    log.debug(f"Unregistering client {connection.uuid}")
    if connection.uuid in connections:
        connections.pop(connection.uuid)

        log.debug(f"Unregistered client {connection.uuid}")
    else:
        log.debug(f"Client {connection.uuid} already unregistered")


async def client_telnet_handler(reader, writer) -> None:
    """
    This handler is for telnet client connections. Upon a client connection this handler is
    the starting point for creating the tasks necessary to handle the client.
    """
    log.debug(f"client_telnet_handler - telnet details are: {dir(reader)}")
    client_details: str = writer.get_extra_info('peername')

    addr, port, *rest = client_details
    log.info(f"Connection established with {addr} : {port} : {rest}")

    # Need to work on better telnet support for regular old telnet clients.
    # Everything so far works great in Mudlet.  Just saying....

    connection: ClientConnection = ClientConnection(addr, port, 'telnet', reader, writer)

    await register_client(connection)

    tasks: list[asyncio.Task] = [
        create_task(connection.client_read(),
                            name=f"{connection.uuid} telnet read"),
        create_task(connection.client_write(),
                            name=f"{connection.uuid} telnet write"),
    ]

    asyncio.current_task().set_name(f"{connection.uuid} ssh handler")

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

