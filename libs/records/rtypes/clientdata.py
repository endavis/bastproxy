# Project: bastproxy
# Filename: libs/records/rtypes/toclient.py
#
# File Description: Holds the client record type
#
# By: Bast
"""Holds the client record type."""

# Standard Library

# 3rd Party

# Project
from libs.records.rtypes.base import BaseRecord
from libs.records.rtypes.log import LogRecord
from libs.records.rtypes.networkdata import NetworkData


class ProcessDataToClient(BaseRecord):
    """a record to a client, this can originate with the mud or internally

    data from the mud will immediately be transformed into this type of record
    will not neccesarily end up going to the client.

    The message format is a NetworkData object
    """

    _SETUP_EVENTS = False

    def __init__(
        self,
        message: "NetworkData",
        clients: list | None = None,
        exclude_clients: list | None = None,
        preamble=True,
        prelogin: bool = False,
        error: bool = False,
        color_for_all_lines=None,
    ):
        """Initialize the class."""
        super().__init__()
        self.message = message
        self.message.parent = self
        self.message.add_parent(self, reset=True)
        # flag to include preamble when sending to client
        self.preamble: bool = preamble
        # flag to send to client before login
        self.prelogin: bool = prelogin
        # flag for this is an error message
        self.error: bool = error
        # This is so that events can set this and it will not be sent to the client
        self.send_to_clients: bool = True
        # clients to send to, a list of client uuids
        # if this list is empty, it goes to all clients
        self.clients: list[str] = clients or []
        # clients to exclude, a list of client uuids
        self.exclude_clients: list[str] = exclude_clients or []
        # This will set the color for all lines to the specified @ color
        self.color_for_all_lines: str = color_for_all_lines or ""
        self.modify_data_event_name = "ev_to_client_data_modify"
        self.read_data_event_name = "ev_to_client_data_read"

        self.sending = False

        self.setup_events()

    def get_attributes_to_format(self):
        """Get the attributes to format for display.

        Returns:
            A list of attribute tuples for formatting.

        """
        attributes = super().get_attributes_to_format()
        attributes[0].extend(
            [
                ("Preamble", "preamble"),
                ("Prelogin", "prelogin"),
                ("Error", "error"),
                ("Send To Clients", "send_to_clients"),
                ("Clients", "clients"),
                ("Exclude Clients", "exclude_clients"),
                ("Color For All Lines", "color_for_all_lines"),
            ]
        )
        return attributes

    def setup_events(self):
        """Set up the events for this record type."""
        if not self._SETUP_EVENTS:
            self.SETUP_EVENTS = True
            self.api("plugins.core.events:add.event")(
                self.modify_data_event_name,
                __name__,
                description=["An event to modify data before it is sent to the client"],
                arg_descriptions={
                    "line": "The line to modify, a NetworkDataLine object"
                },
            )

    # @property
    # def noansi(self):
    #     """
    #     return the message without ansi codes
    #     """
    #     newmessage: list[str] = [
    #         item.noansi for item in self.message
    #     ]
    #     return newmessage

    # @property
    # def color(self):
    #     """
    #     return the message with ansi codes converted to @ color codes
    #     """
    #     newmessage: list[str] = [
    #         item.colorcoded for item in self.message
    #     ]
    #     return newmessage

    def one_line_summary(self):
        """Get a one line summary of the record."""
        return f"{self.__class__.__name__:<20} {self.uuid} {len(self.message)} {self.execute_time_taken:.2f}ms {self.message.get_first_line()!r}"

    def add_client(self, client_uuid: str):
        """Add a client to the list of clients to send to."""
        if client_uuid in self.exclude_clients:
            self.exclude_clients.remove(client_uuid)
        if client_uuid not in self.clients:
            self.clients.append(client_uuid)

    def exclude_client(self, client_uuid):
        """Add a client to the list of clients to exclude."""
        if client_uuid in self.clients:
            self.clients.remove(client_uuid)
        if client_uuid not in self.exclude_clients:
            self.exclude_clients.append(client_uuid)

    def can_send_to_client(self, client_uuid, internal):
        """Returns true if this message can be sent to the client."""
        if client_uuid:
            # Exclude takes precedence over everything else
            if client_uuid in self.exclude_clients:
                return False
            # If the client is a view client and this is an internal message, we don't send it
            # This way view clients don't see the output of commands entered by other clients
            if (
                self.api("plugins.core.clients:client.is.view.client")(client_uuid)
                and internal
            ):
                return False
            # If the client is in the list of clients or self.clients is empty,
            # then we can check to make sure the client is logged in or the prelogin flag is set
            if (not self.clients or client_uuid in self.clients) and (
                self.api("plugins.core.clients:client.is.logged.in")(client_uuid)
                or self.prelogin
            ):
                # All checks passed, we can send to this client
                return True
        return False

    def _exec_(self):
        """Send the message."""
        # If a line came from the mud and it is not a telnet command,
        # pass each line through the event system to allow plugins to modify it
        if data_for_event := [
            line for line in self.message if line.frommud and line.is_io
        ]:
            self.api("plugins.core.events:raise.event")(
                self.modify_data_event_name, data_list=data_for_event, key_name="line"
            )

        if self.send_to_clients:
            SendDataDirectlyToClient(
                self.message, exclude_clients=self.exclude_clients, clients=self.clients
            )()


class SendDataDirectlyToClient(BaseRecord):
    """send data directly to a client

    this bypasses any processing and sends directly to the client.

    The message format is NetworkData instance

    line endings will be added to each line of io before sending to the client
    """

    _SETUP_EVENTS = False

    def __init__(
        self,
        message: "NetworkData",
        clients: list | None = None,
        exclude_clients: list | None = None,
    ):
        """Initialize the class."""
        super().__init__()
        self.message = message
        self.message.parent = self
        self.message.add_parent(self)
        # clients to send to, a list of client uuids
        # if this list is empty, it goes to all clients
        self.clients: list[str] = clients or []
        # clients to exclude, a list of client uuids
        self.exclude_clients: list[str] = exclude_clients or []
        # This will set the color for all lines to the specified @ color
        self.read_data_event_name = "ev_to_client_data_read"

        self.setup_events()

    def setup_events(self):
        """Set up the events for this record type."""
        if not self._SETUP_EVENTS:
            self.SETUP_EVENTS = True
            self.api("plugins.core.events:add.event")(
                self.read_data_event_name,
                __name__,
                description=["An event to see data that was sent to the client"],
                arg_descriptions={
                    "line": "The line to modify, a NetworkDataLine object"
                },
            )

    def one_line_summary(self):
        """Get a one line summary of the record."""
        return f"{self.__class__.__name__:<20} {self.uuid} {len(self.message)} {self.execute_time_taken:.2f}ms {self.message.get_first_line()!r}"

    def can_send_to_client(self, client_uuid, line):
        """Returns true if this message can be sent to the client."""
        if client_uuid:
            # Exclude takes precedence over everything else
            if client_uuid in self.exclude_clients:
                return False
            # If the client is a view client and this is an internal message, we don't send it
            # This way view clients don't see the output of commands entered by other clients
            if (
                client_uuid not in self.clients
                and self.api("plugins.core.clients:client.is.view.client")(client_uuid)
                and line.internal
            ):
                return False
            # If the client is in the list of clients or self.clients is empty,
            # then we can check to make sure the client is logged in or the prelogin flag is set
            if (not self.clients or client_uuid in self.clients) and (
                self.api("plugins.core.clients:client.is.logged.in")(client_uuid)
                or line.prelogin
            ):
                # All checks passed, we can send to this client
                return True
        return False

    def _exec_(self):
        """Send the message."""
        self.message.lock()
        for line in self.message:
            if line.send:
                line.format()
                line.lock()

                clients = self.clients or self.api(
                    "plugins.core.clients:get.all.clients"
                )(uuid_only=True)
                for client_uuid in clients:
                    if self.can_send_to_client(client_uuid, line):
                        self.api("plugins.core.clients:send.to.client")(
                            client_uuid, line
                        )
                    else:
                        LogRecord(
                            f"## NOTE: Client {client_uuid} cannot receive message {self.uuid!s}",
                            level="debug",
                            sources=[__name__],
                        )()

        # If the line is not a telnet command,
        # pass each line through the event system to allow plugins to see
        # what data is being sent to the client
        if data_for_event := [line.line for line in self.message if line.send]:
            self.api("plugins.core.events:raise.event")(
                self.read_data_event_name, data_list=data_for_event, key_name="line"
            )
