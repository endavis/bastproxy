# Project: bastproxy
# Filename: libs/records/rtypes/muddata.py
#
# File Description: Holds the ProcessDataToMud process
#               and the SendDataDirectlyToMud process
#
# By: Bast
"""Holds the tomud record type."""

# Standard Library
import re

# 3rd Party
# Project
from bastproxy.libs.context import capturing_resends, resend_anchor, resend_capture
from bastproxy.libs.records.enums import UpdateFlag
from bastproxy.libs.records.events import TO_MUD_DATA_MODIFY, TO_MUD_DATA_READ
from bastproxy.libs.records.rtypes.base import BaseRecord
from bastproxy.libs.records.rtypes.networkdata import NetworkData, NetworkDataLine


class PendingMudSends:
    """Sends held back while an input is being processed, keyed to the input line they replace."""

    def __init__(self, message: NetworkData) -> None:
        """Keep the message whose lines anchor the held sends."""
        self.message = message
        self.open = True
        self._after: list[tuple[object, list[SendDataDirectlyToMud]]] = []
        self._tail: list[SendDataDirectlyToMud] = []

    def add(self, anchor: object, send: "SendDataDirectlyToMud") -> None:
        """Hold ``send`` until after ``anchor``, or after all lines when it is not one of them."""
        for line in self.message:
            if line is anchor:
                for held_line, sends in self._after:
                    if held_line is line:
                        sends.append(send)
                        return
                self._after.append((line, [send]))
                return
        self._tail.append(send)

    def after(self, line: NetworkDataLine) -> list["SendDataDirectlyToMud"]:
        """Return the sends held for ``line`` in arrival order."""
        for held_line, sends in self._after:
            if held_line is line:
                return list(sends)
        return []

    def tail(self) -> list["SendDataDirectlyToMud"]:
        """Return the sends with no matching line."""
        return list(self._tail)

    def close(self) -> None:
        """Stop accepting held sends."""
        self.open = False


class ProcessDataToMud(BaseRecord):
    """process data being sent to the mud.

    data from a client will be immediately passed through this process
    internal data can use this if it needs to be processed before being sent to the mud.

    it will go through the event system through an event that can
    modify the data before it is sent to the mud
    it may not end up going to the mud depending on the event system

    The message format is NetworkData instance
    """

    MODIFY_EVENT = TO_MUD_DATA_MODIFY

    def __init__(
        self,
        message: "NetworkData",
        show_in_history: bool = True,
        client_id: str | None = None,
        parent: BaseRecord | None = None,
    ) -> None:
        """Initialize the class."""
        super().__init__(parent=parent)
        self.message = message
        self.message.parent = self
        self.message.add_parent(self, reset=True)
        self.show_in_history = show_in_history
        self.client_id = client_id
        self.modify_data_event_name = self.MODIFY_EVENT

    def get_attributes_to_format(self) -> dict[int, list[tuple[str, str]]]:
        """Get the attributes to format for display.

        Returns:
            A list of attribute tuples for formatting.

        """
        attributes = super().get_attributes_to_format()
        attributes[0].extend([("Show in History", "show_in_history"), ("Client ID", "client_id")])
        return attributes

    def one_line_summary(self) -> str:
        """Get a one line summary of the record."""
        return (
            f"{self.__class__.__name__:<20} {self.uuid} {len(self.message)} "
            f"{self.execute_time_taken:.2f}ms {self.message.get_first_line()!r}"
        )

    def seperate_commands(self) -> None:
        """Separate multiple commands in a single line into individual lines."""
        index = 0
        while index < len(self.message):
            line = self.message[index]
            if line.is_io and isinstance(line.line, str):
                split_data = []
                if self.api.command_split_regex:
                    split_data = re.split(self.api.command_split_regex, line.line)
                if len(split_data) > 1:
                    self.addupdate(
                        UpdateFlag.INFO,
                        "split (Split_Char)",
                        extra={
                            "line": line,
                            "newlines": split_data,
                            "msg": "split the data along the command seperator",
                        },
                    )
                    replacement_line = NetworkDataLine(
                        split_data.pop(0),
                        line_type=line.line_type,
                        originated=line.originated,
                    )
                    line.copy_attributes(replacement_line)
                    self.message[index] = replacement_line
                    for newline in split_data:
                        index += 1
                        newdataline = NetworkDataLine(
                            newline,
                            line_type=line.line_type,
                            originated=line.originated,
                        )
                        line.copy_attributes(newdataline)
                        self.message.insert(index, newdataline)
                else:
                    index += 1
            else:
                index += 1

    def _exec_(self) -> None:
        """Process the data before sending to the mud."""
        # If the line came from a client and it is not a telnet command,
        # pass each line through the event system to allow plugins to modify it
        outer = resend_capture.get()
        anchor = resend_anchor.get()
        self.seperate_commands()
        pending = PendingMudSends(self.message)

        try:
            with capturing_resends(pending):
                if data_for_event := [
                    line for line in self.message if line.fromclient and line.is_io
                ]:
                    self.api("plugins.core.events:event.raise")(
                        self.modify_data_event_name,
                        event_args={
                            "showinhistory": self.show_in_history,
                            "client_id": self.client_id,
                        },
                        data_list=data_for_event,
                        key_name="line",
                    )
        finally:
            pending.close()

        send = SendDataDirectlyToMud(
            self.message, client_id=self.client_id, parent=self, pending=pending
        )
        if outer is not None and outer.open:
            outer.add(anchor, send)
            self.addupdate(UpdateFlag.INFO, "send held for the input line it replaces", extra={})
        else:
            send()


class SendDataDirectlyToMud(BaseRecord):
    """send data to the mud.

    this bypasses any processing and sends directly to the mud.

    The message format is NetworkData instance

    line endings will be added to each line of io before sending to the mud

    ``pending`` holds the sends of records nested in the input being processed. They run
    right after the line they replace, or after all lines when none matches (#714).
    """

    READ_EVENT = TO_MUD_DATA_READ

    def __init__(
        self,
        message: "NetworkData",
        client_id: str | None = None,
        parent: BaseRecord | None = None,
        *,
        pending: "PendingMudSends | None" = None,
    ) -> None:
        """Initialize the class."""
        super().__init__(parent=parent)
        self.pending = pending
        self.message = message
        self.message.parent = self
        self.message.add_parent(self)
        self.client_id = client_id
        self.read_data_event_name = self.READ_EVENT

    def get_attributes_to_format(self) -> dict[int, list[tuple[str, str]]]:
        """Get the attributes to format for display.

        Returns:
            A list of attribute tuples for formatting.

        """
        attributes = super().get_attributes_to_format()
        attributes[0].append(("Client ID", "client_id"))
        return attributes

    def _exec_(self) -> None:
        """Send the data to the mud."""
        # Format first: locking the message locks its lines, and a locked line cannot format.
        for line in self.message:
            if line.send:
                line.format(to_mud=True)
        self.message.lock()
        mud_connection = self.api("plugins.core.proxy:mud.connection.get")()
        for line in self.message:
            if mud_connection and line.send:
                mud_connection.send_to(line)
            if self.pending:
                for held in self.pending.after(line):
                    held()
        if self.pending:
            for held in self.pending.tail():
                held()

        # pass each line through the event system to allow plugins to see what
        # data is being sent to the mud
        if data_for_event := [line for line in self.message if line.send]:
            self.api("plugins.core.events:event.raise")(
                self.read_data_event_name,
                event_args={"client_id": self.client_id},
                data_list=data_for_event,
                key_name="line",
            )
