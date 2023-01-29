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
"""

# Standard Library
import asyncio
import json
import logging
from uuid import uuid4

# Third Party

# Project
from libs.messages import Message, messages_to_clients, messages_to_game
from libs.net import telnet

log = logging.getLogger(__name__)

connections = {}


class ClientConnection:
    """
        Each connection when created in async handle_client will instantiate this class.

        Instance variables:
            self.addr is the IP address portion of the client
            self.port is the port portion of the client
            self.conn_type is the type of client connection
            self.state is the current state of the client connection
                Currently used for "softboot" capability
            self.uuid is a str(uuid.uuid4()) for unique session tracking
            self.reader is the asyncio.StreamReader for the connection
            self.writer is the asyncio.StreamWriter for the connection

    """
    def __init__(self, addr, port, conn_type, reader, writer, rows=24):
        self.addr: str = addr
        self.port: str = port
        self.rows: int = rows
        self.login_attempts: int = 0
        self.conn_type: str = conn_type
        self.state: dict[str, bool] = {'connected': True, 'logged in': False}
        self.uuid: str = str(uuid4())
        self.read_only = False
        self.reader: asyncio.StreamReader = reader
        self.writer: asyncio.StreamWriter = writer

    async def notify_connected(self) -> None:
        """
            Create JSON message to notify the game engine of a new client connection.
            Put this message into the messages_to_game asyncio.Queue().
        """
        log.debug('Sending client connected message to game engine.')
        payload: dict[str, str | int] = {
            'uuid': self.uuid,
            'addr': self.addr,
            'port': self.port,
            'rows': self.rows,
        }
        msg: dict[str, str] = {
            'event': 'connection/connected',
#            "secret": WS_SECRET,
            'payload': payload,
        }

        asyncio.create_task(
            messages_to_game.put(
                Message('IO',
                        message=json.dumps(msg, sort_keys=True, indent=4))))
        log.debug('Sent client connected message to game engine.')

    async def notify_disconnected(self) -> None:
        """
            Create JSON Payload to notify the game engine of a client disconnect.
            Put this message into the messages_to_game asyncio.Queue().
        """
        log.debug('Sending client disconnected message to game engine.')
        payload: dict[str, str | int] = {
            'uuid': self.uuid,
            'addr': self.addr,
            'port': self.port,
        }
        msg: dict[str, str] = {
            'event': 'connection/disconnected',
#            "secret": WS_SECRET,
            'payload': payload,
        }

        asyncio.create_task(
            messages_to_game.put(
                Message('IO',
                        message=json.dumps(msg, sort_keys=True, indent=4))))
        log.debug('Sent client disconnected message to game engine.')


async def register_client(connection) -> None:
    """
        Upon a new client connection, we register it to the connections dict.
    """
    log.debug(f"Registering client {connection.uuid}")
    connections[connection.uuid] = connection
    messages_to_clients[connection.uuid] = asyncio.Queue()

    await connection.notify_connected()
    log.debug(f"Registered client {connection.uuid}")


async def unregister_client(connection) -> None:
    """
        Upon client disconnect/quit, we unregister it from the connections dict.
    """
    log.debug(f"Unregistering client {connection.uuid}")
    if connection.uuid in connections:
        connections.pop(connection.uuid)
        messages_to_clients.pop(connection.uuid)

        await connection.notify_disconnected()
        log.debug(f"Unregistered client {connection.uuid}")
    log.debug(f"Client {connection.uuid} already unregistered")


async def client_read(reader, connection) -> None:
    """
        Utilized by the Telnet and SSH client_handlers.

        We want this coroutine to run while the client is connected, so we begin with a while loop
        We first await control back to the loop until we have received some input (or an EOF)
            Mark the connection to disconnected and break out if a disconnect (EOF)
            else we handle the input. Client input packaged into a JSON payload and put into the
            messages_to_game asyncio.Queue()
    """
    log.debug(f"Starting client_read coroutine for {connection.uuid}")
    while connection.state['connected']:
        inp: bytes = await reader.readline()
        log.info("Raw received data in client_read : %s", inp)

        if not inp:  # This is an EOF.  Hard disconnect.
            connection.state['connected'] = False
            return

        if not connection.state['logged in']:
            if inp.strip() == 'bastpass':
                connection.state['logged in'] = True
                # EVENT: client_logged_in
                msg = '#BP: You are now logged in.\r\n'
                asyncio.create_task(
                    messages_to_clients[connection.uuid].put(
                        Message('IO',
                            message=msg)))
                continue

            elif inp.strip() == 'bastviewpass':
                connection.state['logged in'] = True
                connection.read_only = True
                # EVENT: client_logged_in
                msg = '#BP: You are now logged in as view only user.\r\n'
                asyncio.create_task(
                    messages_to_clients[connection.uuid].put(
                        Message('IO',
                            message=msg)))
                continue

            elif connection.login_attempts < 3:
                msg = '#BP: Invalid password. Please try again.\r\n'
                connection.login_attempts = connection.login_attempts + 1
                asyncio.create_task(
                    messages_to_clients[connection.uuid].put(
                        Message('IO',
                            message=msg)))
                continue

            else:
                tasks = asyncio.all_tasks()
                print('Tasks1', pprint.pformat(tasks))
                msg = '#BP: Too many login attempts. Goodbye.\r\n'
                asyncio.create_task(
                    messages_to_clients[connection.uuid].put(
                        Message('IO',
                            message=msg)))
                await asyncio.sleep(1)
                connection.state['connected'] = False

        # This is where we start using events, such as from_client_event

    log.debug(f"Ending client_read coroutine for {connection.uuid}")


async def client_write(writer, connection) -> None:
    """
        Utilized by the Telnet and SSH client_handlers.

        We want this coroutine to run while the client is connected, so we begin with a while loop
        We await for any messages from the game to this client, then write and drain it.
    """
    log.debug('Starting client_write coroutine for %s', connection.uuid)
    while connection.state['connected']:
        msg_obj: Message = await messages_to_clients[connection.uuid].get()
        if msg_obj.is_io:
            writer.write(msg_obj.msg)
            if msg_obj.is_prompt:
                writer.write(telnet.go_ahead())
        elif msg_obj.is_command_telnet:
            writer.write(telnet.iac([msg_obj.command]))

        task = asyncio.create_task(writer.drain())
        logging.getLogger("asyncio").debug(f"Created task {task.get_name()} for write.drain() in client_write")
    log.debug(f"Ending client_write coroutine for {connection.uuid}")


async def client_telnet_handler(reader, writer) -> None:
    """
    This handler is for telnet client connections. Upon a client connection this handler is
    the starting point for creating the tasks necessary to handle the client.
    """
    log.debug(f"client.py:client_telnet_handler - telnet details are: {dir(reader)}")
    client_details: str = writer.get_extra_info('peername')

    addr, port, *rest = client_details
    log.info(f"Connection established with {addr} : {port} : {rest}")

    # Need to work on better telnet support for regular old telnet clients.
    # Everything so far works great in Mudlet.  Just saying....

    connection: ClientConnection = ClientConnection(addr, port, 'telnet', reader, writer)

    await register_client(connection)

    tasks: list[asyncio.Task] = [
        asyncio.create_task(client_read(reader, connection),
                            name=f"{connection.uuid} telnet read"),
        asyncio.create_task(client_write(writer, connection),
                            name=f"{connection.uuid} telnet write"),
    ]

    asyncio.current_task().set_name(f"{connection.uuid} ssh handler")

    # We send an IAC+WONT+ECHO to the client so that it locally echo's it's own input.
    writer.write(telnet.echo_on())

    # Advertise to the client that we will do features we are capable of.
    writer.write(telnet.advertise_features())

    await writer.drain()

    log.debug('Sending welcome message')
    writer.write('#BP: Welcome to Bastproxy.\r\n')
    writer.write('#BP: Please enter your password.\r\n')
    connection.login_attempts += 1
    log.debug('Welcome message sent')

    # We want to .wait until the first task is completed.  "Completed" could be an actual finishing
    # of execution or an exception.  If either the reader or writer "completes", we want to ensure
    # we move beyond this point and cleanup the tasks associated with this client.
    _, rest = await asyncio.wait(tasks, return_when='FIRST_COMPLETED')

    # Once we reach this point one of our tasks (reader/writer) have completed or failed.
    # Remove client from the registration list and perform connection specific cleanup.
    await unregister_client(connection)

    writer.write_eof()
    await writer.drain()
    writer.close()

    for task in rest:
        task.cancel()


