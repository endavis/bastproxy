# Project: bastproxy
# Filename: libs/records/rtypes/clientdata.py
#
# File Description: Holds the client record type
#
# By: Bast
"""Holds the client record type."""

# Standard Library
from typing import Any

# 3rd Party
# Project
from bastproxy.libs.context import client_capture, holding_client_sends
from bastproxy.libs.logger import get_logger
from bastproxy.libs.records.enums import UpdateFlag
from bastproxy.libs.records.events import TO_CLIENT_DATA_MODIFY, TO_CLIENT_DATA_READ
from bastproxy.libs.records.rtypes.base import BaseRecord
from bastproxy.libs.records.rtypes.networkdata import NetworkData, NetworkDataLine

logger = get_logger(__name__)


class PendingClientSends:
    """Client sends held back while the MUD data's modify event runs (#746)."""

    def __init__(self) -> None:
        """Start open and empty."""
        self.open = True
        self._sends: list[BaseRecord] = []

    def add(self, send: BaseRecord) -> None:
        """Hold ``send`` until the MUD data's lines are sent."""
        self._sends.append(send)

    def sends(self) -> list[BaseRecord]:
        """Return the held sends in the order they were made."""
        return list(self._sends)

    def close(self) -> None:
        """Stop accepting held sends."""
        self.open = False

    def release(self) -> None:
        """Run each held send in the order made, bypassing the hold."""
        held, self._sends = self._sends, []
        for send in held:
            BaseRecord.__call__(send)


class ProcessDataToClient(BaseRecord):
    """a record to a client, this can originate with the mud or internally.

    data from the mud will immediately be transformed into this type of record
    will not neccesarily end up going to the client.

    The message format is a NetworkData object
    """

    MODIFY_EVENT = TO_CLIENT_DATA_MODIFY
    READ_EVENT = TO_CLIENT_DATA_READ

    def __init__(
        self,
        message: "NetworkData",
        clients: list | None = None,
        exclude_clients: list | None = None,
    ) -> None:
        """Initialize the class."""
        super().__init__()
        self.message = message
        self.message.parent = self
        self.message.add_parent(self, reset=True)
        # This is so that events can set this and it will not be sent to the client
        self.send_to_clients: bool = True
        # clients to send to, a list of client uuids
        # if this list is empty, it goes to all clients
        self.clients: list[str] = clients or []
        # clients to exclude, a list of client uuids
        self.exclude_clients: list[str] = exclude_clients or []
        self.modify_data_event_name = self.MODIFY_EVENT
        self.read_data_event_name = self.READ_EVENT

        self.sending = False

    def get_attributes_to_format(self) -> dict[int, list[tuple[str, str]]]:
        """Get the attributes to format for display.

        Returns:
            A list of attribute tuples for formatting.

        """
        attributes = super().get_attributes_to_format()
        attributes[0].extend(
            [
                ("Send To Clients", "send_to_clients"),
                ("Clients", "clients"),
                ("Exclude Clients", "exclude_clients"),
            ]
        )
        return attributes

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

    def one_line_summary(self) -> str:
        """Get a one line summary of the record."""
        return (
            f"{self.__class__.__name__:<20} {self.uuid} {len(self.message)} "
            f"{self.execute_time_taken:.2f}ms {self.message.get_first_line()!r}"
        )

    def add_client(self, client_uuid: str) -> None:
        """Add a client to the list of clients to send to."""
        if client_uuid in self.exclude_clients:
            self.exclude_clients.remove(client_uuid)
        if client_uuid not in self.clients:
            self.clients.append(client_uuid)

    def exclude_client(self, client_uuid: str) -> None:
        """Add a client to the list of clients to exclude."""
        if client_uuid in self.clients:
            self.clients.remove(client_uuid)
        if client_uuid not in self.exclude_clients:
            self.exclude_clients.append(client_uuid)

    def _exec_(self) -> None:
        """Send the message."""
        # If a line came from the mud and it is not a telnet command,
        # pass each line through the event system to allow plugins to modify it.
        # Sends made meanwhile are held and go out after this message's lines (#746).
        outer = client_capture.get()
        pending = PendingClientSends()
        try:
            with holding_client_sends(pending):
                if data_for_event := [line for line in self.message if line.frommud and line.is_io]:
                    self.api("plugins.core.events:event.raise")(
                        self.modify_data_event_name, data_list=data_for_event, key_name="line"
                    )
        except BaseException:
            pending.close()
            self._release_or_hand_over(pending, outer)
            raise
        pending.close()

        if self.send_to_clients:
            send = SendDataDirectlyToClient(
                self.message,
                exclude_clients=self.exclude_clients,
                clients=self.clients,
                pending=pending,
            )
            if outer is not None and outer.open:
                outer.add(send)
                self.addupdate(UpdateFlag.INFO, "send held until the outer MUD data is sent")
            else:
                send()
        else:
            self._release_or_hand_over(pending, outer)

    def _release_or_hand_over(self, pending: PendingClientSends, outer: Any) -> None:
        """Run the held sends, or give them to an open outer capture."""
        if outer is not None and outer.open:
            for held in pending.sends():
                outer.add(held)
        else:
            pending.release()


class SendDataDirectlyToClient(BaseRecord):
    """send data directly to a client.

    this bypasses any processing and sends directly to the client.

    The message format is NetworkData instance

    line endings will be added to each line of io before sending to the client

    While a ProcessDataToClient modify event runs, a call is held and runs after that
    message's lines are sent. ``pending`` holds the sends made during this message's own
    modify event; they run after its lines and before the read event (#746).
    """

    READ_EVENT = TO_CLIENT_DATA_READ

    def __init__(
        self,
        message: "NetworkData",
        clients: list | None = None,
        exclude_clients: list | None = None,
        *,
        pending: PendingClientSends | None = None,
    ) -> None:
        """Initialize the class."""
        super().__init__()
        self.pending = pending
        self.message = message
        self.message.parent = self
        self.message.add_parent(self)
        # clients to send to, a list of client uuids
        # if this list is empty, it goes to all clients
        self.clients: list[str] = clients or []
        # clients to exclude, a list of client uuids
        self.exclude_clients: list[str] = exclude_clients or []
        # This will set the color for all lines to the specified @ color
        self.read_data_event_name = self.READ_EVENT

    def __call__(self, *args: Any, **kwargs: Any) -> None:
        """Hold the send while MUD data is being processed, else run it."""
        capture = client_capture.get()
        if capture is not None and capture.open:
            capture.add(self)
            self.addupdate(
                UpdateFlag.INFO, "send held until the MUD data's lines are sent", extra={}
            )
            return
        super().__call__(*args, **kwargs)

    def one_line_summary(self) -> str:
        """Get a one line summary of the record."""
        return (
            f"{self.__class__.__name__:<20} {self.uuid} {len(self.message)} "
            f"{self.execute_time_taken:.2f}ms {self.message.get_first_line()!r}"
        )

    def can_send_to_client(self, client_uuid: str, line: NetworkDataLine) -> bool:
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
                self.api("plugins.core.clients:client.is.logged.in")(client_uuid) or line.prelogin
            ):
                # All checks passed, we can send to this client
                return True
        return False

    def _exec_(self) -> None:
        """Send the message."""
        try:
            # Format first: locking the message locks its lines, and a locked line cannot format.
            for line in self.message:
                if line.send:
                    line.format()
            self.message.lock()
            for line in self.message:
                if line.send:
                    clients = self.clients or self.api("plugins.core.clients:client.list")(
                        uuid_only=True
                    )
                    for client_uuid in clients:
                        if self.can_send_to_client(client_uuid, line):
                            self.api("plugins.core.clients:client.send")(client_uuid, line)
                        else:
                            logger.debug(
                                "## NOTE: Client %s cannot receive message %s",
                                client_uuid,
                                self.uuid,
                            )
        finally:
            if self.pending:
                self.pending.release()

        # If the line is not a telnet command,
        # pass each line through the event system to allow plugins to see
        # what data is being sent to the client
        if data_for_event := [line for line in self.message if line.send]:
            self.api("plugins.core.events:event.raise")(
                self.read_data_event_name, data_list=data_for_event, key_name="line"
            )
