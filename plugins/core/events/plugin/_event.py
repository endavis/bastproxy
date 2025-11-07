# -*- coding: utf-8 -*-
# Project: bastproxy
# Filename: plugins/core/events/_event.py
#
# File Description: Holds base classes for event items
#
# By: Bast
"""
Holds base classes for an event to raise

The created_by attribute is the name of the plugin or module that created the event
It can be updated in two ways, by using the api plugins.core.events:add:event
    or when the event is raised and a calledfrom argument is passed and created_by is not already been set
"""
# Standard Library
from typing import TYPE_CHECKING, Callable

# 3rd Party

# Project
from libs.api import API
from libs.records import LogRecord
from libs.callback import Callback
from plugins.core.events.libs.process._raisedevent import ProcessRaisedEvent
from plugins.core.events.libs.data._event import EventDataRecord

class Event:
    """
    Base class for an event
    """
    def __init__(self, name: str, created_by: str ='', description: list | None = None, arg_descriptions: dict[str, str] | None = None):
        """
        name: the name of the event
        created_by: it should be the __name__ of the module or the plugin id for easy identification
        description: a list of strings that describe the event
        arg_descriptions: a dictionary of argument names and descriptions
        """
        self.name: str = name
        # it should be the __name__ of the module or the plugin id for easy identification
        self.created_by: str = created_by
        self.description = description or []
        self.arg_descriptions = arg_descriptions or {}

        self.owner_id: str = f"{__name__}:{self.name}"
        self.api = API(owner_id=self.owner_id)
        self.priority_dictionary = {}
        self.raised_count = 0
        # NOTE : this is an unbound dictionary, may need to limit the size
        #           because of how many events will be raised
        self.raised_events = {}
        self.current_callback = None
        self.active_event = None

    def get_active_event(self):
        """
        get the active event
        """
        return self.active_event

    def count(self) -> int:
        """
        return the number of functions registered to this event
        """
        return sum(len(v) for v in self.priority_dictionary.values())

    def isregistered(self, func) -> bool:
        """
        check if a function is registered to this event
        """
        return any(
            func in self.priority_dictionary[priority]
            for priority in self.priority_dictionary
        )

    def isempty(self) -> bool:
        """
        check if an event has no functions registered
        """
        return not any(
            self.priority_dictionary[priority]
            for priority in self.priority_dictionary
        )

    def register(self, func: Callable, func_owner_id: str, prio: int = 50) -> bool:
        """
        register a function to this event container
        """
        priority = prio or 50
        if priority not in self.priority_dictionary:
            self.priority_dictionary[priority] = {}

        call_back = Callback(func.__name__, func_owner_id, func)

        if call_back not in self.priority_dictionary[priority]:
            # This is a list of functions that are registered to this event at this priority
            # It is used to ensure that a function is not registered twice
            # Each time the event is invoked, the dictionary item will be set to True
            # when the function has been called. This is used to ensure that all functions
            # are called at least once before the event is finished
            self.priority_dictionary[priority][call_back]= False
            LogRecord(f"{self.name} - register function {call_back} with priority {priority}",
                      level='debug', sources=[call_back.owner_id, self.created_by])()
            return True

        return False

    def unregister(self, func) -> bool:
        """
        unregister a function from this event container
        """
        # print(f"unregister - {self.name} - {func.__name__}")
        for priority in self.priority_dictionary:
            # print(f"unregister - {self.name} - {func.__name__} - {priority}")
            for call_back in self.priority_dictionary[priority]:
                # print(f"unregister - {self.name} - {func.__name__} - {priority} - {call_back}")
                # print(f"{call_back == func = }")
                if call_back == func:
                    LogRecord(f"unregister - {self.name} - unregister function {func} with priority {priority}",
                              level='debug', sources=[call_back.owner_id, self.created_by])()
                    del self.priority_dictionary[priority][call_back]
                    return True

        LogRecord(f"unregister - {self.name} - could not find function {func.__name__}",
                  level='error', sources=[self.created_by])()
        return False

    def getownerregistrations(self, owner_id):
        registrations = []
        for priority in self.priority_dictionary:
            registrations.extend(
                {'function_name': call_back.name, 'priority': priority}
                for call_back in self.priority_dictionary[priority]
                if call_back.owner_id == owner_id
            )
        return registrations

    def removeowner(self, owner_id):
        """
        remove all functions related to a owner
        """
        plugins_to_unregister = []
        for priority in self.priority_dictionary:
            plugins_to_unregister.extend(
                call_back
                for call_back in self.priority_dictionary[priority]
                if call_back.owner_id == owner_id
            )
        for event_function in plugins_to_unregister:
            self.api('plugins.core.events:unregister.from.event')(self.name, event_function.func)

    def detail(self) -> list[str]:
        """
        format a detail of the event
        """
        header_color = self.api('plugins.core.settings:get')('plugins.core.commands', 'output_header_color')
        subheader_color = self.api('plugins.core.settings:get')('plugins.core.commands', 'output_subheader_color')

        description = []
        for i, line in enumerate(self.description):
            if not line:
                continue
            if i == 0:
                description.append(f"{'Description':<13} : {line}")
            else:
                description.append(f"{'':<13}   {line}")

        message: list[str] = [
            f"{'Event':<13} : {self.name}",
            *description,
            f"{'Created by':<13} : {self.created_by}",
            f"{'Raised':<13} : {self.raised_count}",
            '',
            self.api('plugins.core.utils:center.colored.string')(
                '@x86Registrations@w', '-', 60, filler_color=header_color
            ),
            f"{'priority':<13} : {'owner':<25} - function name",
            subheader_color + '-' * 60 + '@w',
        ]
        function_message: list[str] = []
        key_list = self.priority_dictionary.keys()
        key_list = sorted(key_list)
        for priority in key_list:
            function_message.extend(
                f"{priority:<13} : {call_back.owner_id:<25} - {call_back.name}"
                for call_back in self.priority_dictionary[priority]
            )
        if not function_message:
            message.append('None')
        else:
            message.extend(function_message)
        message.extend((header_color + '-' * 60 + '@w', ''))
        message.append(self.api('plugins.core.utils:center.colored.string')('@x86Data Keys@w', '-', 60, filler_color=header_color))
        if self.arg_descriptions and 'None' not in self.arg_descriptions:
            message.extend(
                f"@C{arg:<13}@w : {self.arg_descriptions[arg]}"
                for arg in self.arg_descriptions
            )
        elif 'None' in self.arg_descriptions:
            message.append('None')
        else:
            message.append('Unknown')
        message.append(header_color + '-' * 60 + '@w')

        # if self.raised_data:
        #     message.append('')
        #     message.append(self.api('plugins.core.utils:center.colored.string')('@x86Last 10 Raised Events@w', '-', 60, filler_color=header_color))
        #     for i, data in enumerate(self.raised_data.get()):
        #         if i > 0:
        #             message.append('')
        #         message.extend(data.format_simple())
        #     message.append(header_color + '-' * 60 + '@w')

        return message

    def reset_event(self):
        """
        reset the event
        """
        for priority in self.priority_dictionary:
            for call_back in self.priority_dictionary[priority]:
                self.priority_dictionary[priority][call_back] = False

    def raise_priority(self, priority, already_done: bool) -> bool:
        """
        raise the event at a specific priority
        """
        found = False
        for call_back in list(self.priority_dictionary[priority].keys()):
            try:
                # A callback should call the api 'plugins.core.events:get:current:event'
                # which returns event_name, EventDataRecord
                # If the registered event changes the data, it should snapshot it with addupdate
                if call_back in self.priority_dictionary[priority] \
                        and not self.priority_dictionary[priority][call_back] \
                        and self.current_callback != call_back:
                    self.current_callback = call_back
                    self.priority_dictionary[priority][call_back] = True
                    call_back.execute()
                    found = True
                    if already_done:
                        LogRecord(f"raise_event - event {self.name} with function {call_back.owner_id}:{call_back.name} was called out of order at priority {priority}",
                                    level='warning', sources=[call_back.owner_id, self.created_by])()
                        LogRecord(f"    this is likely due to a function being registered at priority {priority} during the execution of the event",
                                    level='warning', sources=[call_back.owner_id, self.created_by])()

            except Exception:  # pylint: disable=broad-except
                LogRecord(f"raise_event - event {self.name} with function {call_back.name} raised an exception",
                            level='error', sources=[call_back.owner_id, self.created_by], exc_info=True)()

        return found

    def raise_event(self, data: dict | EventDataRecord, actor: str, data_list=None, key_name=None) -> EventDataRecord | None:
        """
        raise this event
        """
        self.raised_count = self.raised_count + 1

        # If data is not a dict or EventDataRecord object, log an error and the event will not be processed
        if not isinstance(data, EventDataRecord) and not isinstance(data, dict):
            LogRecord(f"raise_event - event {self.name} raised by {self.called_from} did not pass a dict or EventDataRecord object",
                        level='error', sources=[self.created_by, 'plugins.core.events'])()
            LogRecord(
                "The event will not be processed",
                level='error',
                sources=[self.created_by, 'plugins.core.events'],
            )()
            return None

        if not isinstance(data, EventDataRecord):
            data = EventDataRecord(owner_id=actor, event_name=self.name, data=data)

        # if the created_by is not set, set it to the calledfrom argument
        if actor and not self.created_by:
            self.created_by = actor

        self.active_event = ProcessRaisedEvent(self, data, actor) # type: ignore
        uuid = self.active_event.uuid
        self.raised_events[uuid] = self.active_event
        self.active_event(actor, data_list=data_list, key_name=key_name)
        self.active_event = None
        return self.raised_events[uuid]
