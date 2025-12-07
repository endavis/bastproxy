# Project: bastproxy
# Filename: libs/records/rtypes/change.py
#
# File Description: Holds the change record type
#
# By: Bast
"""Holds the change record type
"""

# Standard Library
import traceback
import pprint
import contextlib

# 3rd Party

# Project
from libs.api import API
from pydatatracker import ChangeLogEntry


class RecordChangeLogEntry(ChangeLogEntry):
    """a update event for a record
    flag: one of 'Modify', 'Set Flag', 'Info'
    action: a description of what was updated
    actor: the item that send the update (likely a plugin)
    extra: any extra info about this update
    data: the new data

    will automatically add the time and last 5 stack frames
    """

    def __init__(
        self,
        parent,
        flag: str,
        action: str,
        extra: dict | None = None,
        data=None,
        call_stack=None,
    ):
        if not extra:
            extra = {}
        if "action" not in extra:
            extra["action"] = action

        super().__init__(parent._tracking_uuid)
        self.parent = parent
        self.flag = flag
        self.api = API(owner_id=f"{self.__class__.__name__}:{self.uuid}")
        self.action = action
        self.extra = {}
        if extra:
            self.extra |= extra
        self.data = data
        # Extract the last 15 stack frames
        if call_stack:
            self.stack = self.stack
        else:
            self.stack = self.fix_stack(traceback.format_stack(limit=15))
        self.actor = self.find_relevant_actor(self.stack)
        self.event_stack = []
        with contextlib.suppress(Exception):
            if self.api("libs.api:has")("plugins.core.events:get.event.stack"):
                self.event_stack = self.api("plugins.core.events:get.event.stack")()

    def __hash__(self):
        return hash(f"{self.__class__.__name__}:{self.uuid}")

    def __eq__(self, value: object) -> bool:
        return (
            self.uuid == value.uuid
            if isinstance(value, RecordChangeLogEntry)
            else False
        )

    def __lt__(self, value: object) -> bool:
        return self.created_time < value.created_time if hasattr(value, "created_time") else False  # type: ignore

    def fix_stack(self, stack):
        new_stack = []
        # don't need the last 2 lines
        for line in stack:
            new_stack.extend(line.splitlines() if line else [])
        return new_stack[:-2]

    def find_relevant_actor(self, stack):
        not_relevant = ["libs/records/", "libs/data", "libs/process", "libs/tracking"]
        found_actor = ""
        for line in [line for line in stack if "File" in line]:
            if (
                all((line.find(actor) == -1) for actor in not_relevant)
                and "addupdate" not in stack[stack.index(line) + 1]
            ):
                found_actor = [line, stack[stack.index(line) + 1]]
        return found_actor

    def __str__(self):
        return f"{self.flag} - {self.action} - {self.data} - {self.extra}"

    def format(self):
        """Format the change record"""

        if self.flag == "Modify":
            return f"updated {self.action}"
        if self.flag == "Set Flag":
            return f"set {self.action} to {self.data}"
        if self.flag == "Info":
            return f"{self.action}"

    def format_detailed(
        self,
        show_data: bool = False,
        show_stack: bool = False,
        data_lines_to_show: int = 10,
    ):
        """Format the change record"""

        args = self.api("plugins.core.commands:get.current.command.args")()
        if "show_data" in args:
            show_data = args["show_data"]
        if "show_stack" in args:
            show_stack = args["show_stack"]
        if "data_lines_to_show" in args:
            data_lines_to_show = int(args["data_lines_to_show"])

        actor_msg = []
        if self.actor:
            actor = self.api("plugins.core.utils:dedent.list.of.strings")(self.actor)
            actor_msg.extend((f"{'Actor':<15} : {actor[0]}", f"{'':<15} : {actor[1]}"))
        else:
            actor_msg.append(f"{'Actor':<15} : Unknown")

        tmsg = [
            f"{'UUID':<15} : {self.uuid}",
            f"{'Record':<15} : {self.parent.__class__.__name__}:{self.parent.uuid}",
            f"{'Flag':<15} : {self.flag}",
            *actor_msg,
            f"{'Action':<15} : {self.action}",
            f"{'Time Taken':<15} : {self.created_time}",
        ]
        if self.extra:
            tmsg.append(f"{'Extra':<15} : {self.extra}")
        if self.event_stack:
            tmsg.append(
                f"{'Event Stack':<15} :",
            )
            tmsg.extend([f"{'':<15} : {event}" for event in self.event_stack])
        if show_data and self.data is not None:
            if isinstance(self.data, list) and data_lines_to_show != -1:
                data = self.data[:data_lines_to_show]
            else:
                data = self.data
            tmsg.append(f"{'Data':<15} :")
            tmsg.extend(
                f"{'':<15} : {line}"
                for line in pprint.pformat(data, width=120).splitlines()
            )
        if show_stack and self.stack:
            tmsg.append(f"{'Stack':<15} :")
            tmsg.extend([f"{'':<15} {line}" for line in self.stack if line.strip()])

        return tmsg
