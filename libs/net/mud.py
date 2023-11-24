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

# Third Party

# Project
from libs.net import telnet
from libs.api import API
from libs.records import ToClientRecord, LogRecord, ToMudRecord
from libs.net.networkdata import NetworkData



class MudConnection:
    """
        Each connection when created in async handle_client will instantiate this class.

        Instance variables:
            self.addr is the IP address portion of the client
            self.port is the port portion of the client
            self.conn_type is the type of client connection
                close connection on 3 failed attempts
            self.state is the current state of the client connection
            self.reader is the asyncio.StreamReader for the connection
            self.writer is the asyncio.StreamWriter for the connection

    """
    def __init__(self, addr, port):
        self.addr: str = addr
        self.port: str = port
        self.api = API(owner_id=f"{__name__}")
        #self.conn_type: str = conn_type
        # self.state: dict[str, bool] = {'connected': True}
        self.connected = False
        self.send_queue: asyncio.Queue[NetworkData] = asyncio.Queue()
        self.connected_time =  datetime.datetime.now(datetime.timezone.utc)
        #self.reader: asyncio.StreamReader = reader
        #self.writer: asyncio.StreamWriter = writer
        #print(self.writer.protocol._extra)  # type: ignore
        # rows = self.writer.protocol._extra['rows']
        # term = self.writer.protocol._extra['TERM']

    def send_to(self, data: ToMudRecord) -> None:
        """
        add data to the queue
        """
        if not self.connected:
            LogRecord('send_to - Mud is not connected', level='debug', sources=[__name__])()
            return
        loop = asyncio.get_event_loop()
        if data.is_io:
            message = NetworkData(data.message_type, message=''.join(data))
            loop.call_soon_threadsafe(self.send_queue.put_nowait, message)
        else:
            for i in data:
                message = NetworkData(data.message_type, message=i)
                loop.call_soon_threadsafe(self.send_queue.put_nowait, message)

    async def setup_mud(self) -> None:
        """
        send telnet options
        send welcome message to client
        ask for password
        """

        if features := telnet.advertise_features():
            LogRecord(
                "setup_mud - Sending telnet features",
                level='debug',
                sources=[__name__],
            )()
            ToMudRecord([features], message_type='COMMAND-TELNET')('libs.net.client:setup_client')
            LogRecord(
                "setup_mud - telnet features sent",
                level='debug',
                sources=[__name__],
            )()

        await self.writer.drain()

    async def mud_read(self) -> None:
        """
            Utilized by the Telnet mud_handler.

            We want this coroutine to run while the mud is connected, so we begin with a while loop
        """
        LogRecord(
            "mud_read - Starting coroutine for mud",
            level='debug',
            sources=[__name__],
        )()

        while self.connected:
            inp: bytes = await self.reader.readline()
            LogRecord(f"client_read - Raw received data in mud_read : {inp}", level='debug', sources=[__name__])()
            LogRecord(f"client_read - inp type = {type(inp)}", level='debug', sources=[__name__])()
            logging.getLogger("data.mud").info(f"{'from_mud':<12} : {inp}")

            if not inp:  # This is an EOF.  Hard disconnect.
                self.connected = False
                return

            # this is where we start with ToClientRecord
            ToClientRecord(inp, internal=False)('libs.net.mud:mud_read')

        LogRecord(
            "mud_read - Ending coroutine",
            level='debug',
            sources=[__name__]
        )()

    async def mud_write(self) -> None:
        """
            Utilized by the Telnet and SSH client_handlers.

            We want this coroutine to run while the client is connected, so we begin with a while loop
            We await for any messages from the game to this client, then write and drain it.
        """
        LogRecord(
            "client_write - Starting coroutine for mud_write",
            level='debug',
            sources=[__name__],
        )()
        while self.connected:
            msg_obj: NetworkData = await self.send_queue.get()
            if msg_obj.is_io:
                if msg_obj.msg:
                    LogRecord(f"client_write - Writing message to mud: {msg_obj.msg}", level='debug', sources=[__name__])()
                    LogRecord(f"client_write - type of msg_obj.msg = {type(msg_obj.msg)}", level='debug', sources=[__name__])()
                    self.writer.write(msg_obj.msg)  # type: ignore
                    logging.getLogger("data.mud").info(f"{'to_mud':<12} : {msg_obj.msg}")
                    if msg_obj.is_prompt:
                        self.writer.write(telnet.go_ahead())
                        logging.getLogger(f"data.{self.uuid}").info(f"{'to_client':<12} : {telnet.goahead()}")  # type: ignore
                else:
                    LogRecord(
                        "client_write - No message to write to client.",
                        level='debug',
                        sources=[__name__],
                    )()

            elif msg_obj.is_command_telnet:
                LogRecord(f"client_write - Writing telnet option to mud: {msg_obj.msg}", level='debug', sources=[__name__])()
                LogRecord(f"client_write - type of msg_obj.msg = {type(msg_obj.msg)}", level='debug', sources=[__name__])()
                self.writer.send_iac(msg_obj.msg)  # type: ignore
                logging.getLogger("data.mud").info(f"{'to_client':<12} : {msg_obj.msg}")

            self.api('libs.asynch:task.add')(self.writer.drain, name="mud.write.drain")

        LogRecord(
            "client_write - Ending coroutine",
            level='debug',
            sources=[__name__]
        )()


async def mud_telnet_handler(reader, writer) -> None:
    """
    This handler is for telnet client connections. Upon a client connection this handler is
    the starting point for creating the tasks necessary to handle the client.
    """
    client_details: str = writer.get_extra_info('peername')

    addr, port, *rest = client_details
    #connection: ClientConnection = ClientConnection(addr, port, 'telnet', reader, writer)
    #LogRecord(f"Connection established with {addr} : {port} : {rest} : uuid - {connection.uuid}", level='warning', sources=[__name__])()

    # Need to work on better telnet support for regular old telnet clients.
    # Everything so far works great in Mudlet.  Just saying....

    # tasks = asyncio.all_tasks()
    # print(tasks)

    # tasks: list[asyncio.Task] = [
    #     create_task(connection.client_read(),
    #                         name=f"{connection.uuid} telnet read"),
    #     create_task(connection.client_write(),
    #                         name=f"{connection.uuid} telnet write"),
    # ]

    # asyncio.current_task().set_name(f"{connection.uuid} telnet client handler")  # type: ignore

    # await connection.setup_client()

    # We want to .wait until the first task is completed.  "Completed" could be an actual finishing
    # of execution or an exception.  If either the reader or writer "completes", we want to ensure
    # we move beyond this point and cleanup the tasks associated with this client.
    # _, rest = await asyncio.wait(tasks, return_when='FIRST_COMPLETED')

    # Once we reach this point one of our tasks (reader/writer) have completed or failed.
    # Remove client from the registration list and perform connection specific cleanup.
    # await unregister_client(connection)

    # try:
    #     writer.write_eof()
    #     await writer.drain()
    #     writer.close()
    # except AttributeError:
    #     # The transport was already closed
    #     pass

    # for task in rest:
    #     task.cancel()

    # await asyncio.sleep(1)

