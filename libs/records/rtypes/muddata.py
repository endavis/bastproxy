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
from libs.records.rtypes.base import BaseRecord
from libs.records.rtypes.networkdata import NetworkData, NetworkDataLine


class ProcessDataToMud(BaseRecord):
    """process data being sent to the mud
    data from a client will be immediately passed through this process
    internal data can use this if it needs to be processed before being sent to the mud.

    it will go through the event system through an event that can
    modify the data before it is sent to the mud
    it may not end up going to the mud depending on the event system

    The message format is NetworkData instance
    """

    _SETUP_EVENTS = False

    def __init__(
        self,
        message: "NetworkData",
        show_in_history: bool = True,
        client_id=None,
        parent=None,
    ):
        """Initialize the class."""
        super().__init__(parent=parent)
        self.message = message
        self.message.parent = self
        self.message.add_parent(self, reset=True)
        self.show_in_history = show_in_history
        self.client_id = client_id
        self.modify_data_event_name = "ev_to_mud_data_modify"
        self.setup_events()

    def get_attributes_to_format(self):
        attributes = super().get_attributes_to_format()
        attributes[0].extend(
            [("Show in History", "show_in_history"), ("Client ID", "client_id")]
        )
        return attributes

    def one_line_summary(self):
        """Get a one line summary of the record."""
        return f"{self.__class__.__name__:<20} {self.uuid} {len(self.message)} {self.execute_time_taken:.2f}ms {self.message.get_first_line()!r}"

    def setup_events(self):
        if not self._SETUP_EVENTS:
            self.SETUP_EVENTS = True
            self.api("plugins.core.events:add.event")(
                self.modify_data_event_name,
                __name__,
                description=["An event to modify data before it is sent to the mud"],
                arg_descriptions={
                    "line": "The line to modify, a NetworkDataLine instance",
                    "showinhistory": "If the data should be shown in the history",
                    "client_id": "The client id it came from",
                },
            )

    def seperate_commands(self):
        index = 0
        while index < len(self.message):
            line = self.message[index]
            if line.is_io and isinstance(line.line, str):
                split_data = []
                if self.api.command_split_regex:
                    split_data = re.split(self.api.command_split_regex, line.line)
                if len(split_data) > 1:
                    self.addupdate(
                        "Info",
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

    def _exec_(self):
        """Process the data before sending to the mud."""
        # If the line came from a client and it is not a telnet command,
        # pass each line through the event system to allow plugins to modify it
        self.seperate_commands()

        if data_for_event := [
            line for line in self.message if line.fromclient and line.is_io
        ]:
            self.api("plugins.core.events:raise.event")(
                self.modify_data_event_name,
                event_args={
                    "showinhistory": self.show_in_history,
                    "client_id": self.client_id,
                },
                data_list=data_for_event,
                key_name="line",
            )

        SendDataDirectlyToMud(self.message, client_id=self.client_id, parent=self)()


class SendDataDirectlyToMud(BaseRecord):
    """send data to the mud
    this bypasses any processing and sends directly to the mud.

    The message format is NetworkData instance

    line endings will be added to each line of io before sending to the mud
    """

    _SETUP_EVENTS = False

    def __init__(
        self,
        message: "NetworkData",
        show_in_history: bool = True,
        client_id=None,
        parent=None,
    ):
        """Initialize the class."""
        super().__init__(parent=parent)
        self.message = message
        self.message.parent = self
        self.message.add_parent(self)
        self.read_data_event_name = "ev_to_mud_data_read"
        self.setup_events()

    def setup_events(self):
        if not self._SETUP_EVENTS:
            self.SETUP_EVENTS = True
            self.api("plugins.core.events:add.event")(
                self.read_data_event_name,
                __name__,
                description=["An event to see data that was sent to the mud"],
                arg_descriptions={
                    "line": "The line to modify, a NetworkDataLine instance"
                },
            )

    def _exec_(self):
        """Send the data to the mud."""
        self.message.lock()
        if mud_connection := self.api("plugins.core.proxy:get.mud.connection")():
            for line in self.message:
                if line.send:
                    line.format()
                    line.lock()
                    mud_connection.send_to(line)

        # pass each line through the event system to allow plugins to see what
        # data is being sent to the mud
        if data_for_event := [line.line for line in self.message if line.send]:
            self.api("plugins.core.events:raise.event")(
                self.read_data_event_name, data_list=data_for_event, key_name="line"
            )
