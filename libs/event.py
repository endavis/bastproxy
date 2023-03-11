# -*- coding: utf-8 -*-
# Project: bastproxy
# Filename: libs/event.py
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

# 3rd Party

# Project
from libs.api import API
from libs.records import LogRecord, EventArgsRecord
from libs.callback import Callback

class Event:
    """
    a base class for an event and it's arguments
    """
    def __init__(self, name, created_by=None, description=None, arg_descriptions=None):
        self.name = name
        self.api = API()
        # this is the plugin or module that created the event
        # it should be the __name__ of the module or plugin
        self.created_by = created_by
        self.priority_dictionary = {}
        self.raised_count = 0
        self.description = description
        if not arg_descriptions:
            self.arg_descriptions = {}
        else:
            self.arg_descriptions = arg_descriptions

    def count(self):
        """
        return the number of functions registered to this event
        """
        count = 0
        for priority in self.priority_dictionary:
            count = count + len(self.priority_dictionary[priority])

        return count

    def isregistered(self, func):
        """
        check if a function is registered to this event
        """
        for priority in self.priority_dictionary:
            if func in self.priority_dictionary[priority]:
                return True

        return False

    def isempty(self):
        """
        check if an event has no functions registered
        """
        for priority in self.priority_dictionary:
            if self.priority_dictionary[priority]:
                return False

        return True

    def register(self, func, func_plugin_id, prio=50):
        """
        register a function to this event container
        """
        if not prio:
            priority = 50
        else:
            priority = prio

        if priority not in self.priority_dictionary:
            self.priority_dictionary[priority] = []

        event_function = Callback(func.__name__, func_plugin_id, func)

        if event_function not in self.priority_dictionary[priority]:
            self.priority_dictionary[priority].append(event_function)
            LogRecord(f"{self.name} - register function {event_function} with priority {priority}",
                      level='debug', sources=[event_function.plugin_id, self.created_by]).send()
            return True

        return False

    def unregister(self, func):
        """
        unregister a function from this event container
        """
        for priority in self.priority_dictionary:
            if func in self.priority_dictionary[priority]:
                event_function = self.priority_dictionary[priority][self.priority_dictionary[priority].index(func)]
                LogRecord(f"unregister - {self.name} - unregister function {event_function} with priority {priority}",
                          level='debug', sources=[event_function.plugin_id, self.created_by]).send()
                self.priority_dictionary[priority].remove(event_function)
                return True

        LogRecord(f"unregister - {self.name} - could not find function {func.__name__}",
                  level='error', sources=[self.created_by]).send()
        return False

    def removeplugin(self, plugin):
        """
        remove all functions related to a plugin
        """
        plugins_to_unregister = []
        for priority in self.priority_dictionary:
            for event_function in self.priority_dictionary[priority]:
                if event_function.plugin_id == plugin:
                    plugins_to_unregister.append(event_function)

        for event_function in plugins_to_unregister:
            self.api('plugins.core.events:unregister:from:event')(self.name, event_function.func)

    def detail(self):
        """
        format a detail of the event
        """
        message = []
        message.append(f"{'Event':<13} : {self.name}")
        message.append(f"{'Description':<13} : {self.description}")
        message.append(f"{'Created by':<13} : {self.created_by}")
        message.append(f"{'Raised':<13} : {self.raised_count}")
        message.append('')
        message.append(self.api('plugins.core.utils:center:colored:string')('@x86Registrations@w', '-', 60, filler_color='@B'))
        message.append(f"{'priority':<13} : {'plugin':<25} - {'function name'}")
        message.append('-' * 60)
        function_message = []
        key_list = self.priority_dictionary.keys()
        key_list = sorted(key_list)
        for priority in key_list:
            for event_function in self.priority_dictionary[priority]:
                function_message.append(f"{priority:<13} : {event_function.plugin_id:<25} - {event_function.name}")

        if not function_message:
            message.append('None')
        else:
            message.extend(function_message)
        message.append('@B' + '-' * 60)

        message.append('')

        message.append(self.api('plugins.core.utils:center:colored:string')('@x86Arguments@w', '-', 60, filler_color='@B'))
        if self.arg_descriptions and 'None' not in self.arg_descriptions:
            for arg in self.arg_descriptions:
                message.append(f"@C{arg:<13}@w : {self.arg_descriptions[arg]}")
        elif 'None' in self.arg_descriptions:
            message.append('None')
        else:
            message.append('Unknown')
        message.append('@B' + '-' * 60)

        return message

    def raise_event(self, data, calledfrom):
        """
        raise this event
        """
        self.raised_count = self.raised_count + 1

        # if the created_by is not set, set it to the calledfrom argument
        if calledfrom and not self.created_by:
            self.created_by = calledfrom

        # Any standard dictionary will be converted to a EventArgsRecord object
        if not data:
            data = {}

        if not isinstance(data, EventArgsRecord) and not isinstance(data, dict):
            LogRecord(f"raise_event - event {self.name} raised by {calledfrom} did not pass a dict or EventArgsRecord object",
                        level='error', sources=[calledfrom, self.created_by, 'plugins.core.events']).send()
            LogRecord(f"The event will not be processed", level='error', sources=[calledfrom, self.created_by, 'plugins.core.events']).send()
            return

        if not isinstance(data, EventArgsRecord) and isinstance(data, dict):
            args = EventArgsRecord(plugin_id=calledfrom, event_name=self.name, data=data)

        log_savestate = self.api('libs.api:run:as:plugin')('plugins.core.events', 'setting:get')('log_savestate')
        if '_savestate' in self.name and log_savestate:
            LogRecord(f"raise_event - event {self.name} raised by {calledfrom} with args {args}",
                      level='debug', sources=[calledfrom, self.created_by]).send()
        keys = self.priority_dictionary.keys()
        if keys:
            keys = sorted(keys)
            for priority in keys:
                for event_function in self.priority_dictionary[priority][:]:
                    try:
                        # Args is a record that acts like a dictionary can now be updated.
                        # If the registered event changes the args, it should snapshot it with addchange
                        event_function.execute(args)
                    except Exception:  # pylint: disable=broad-except
                        LogRecord(f"raise_event - event {self.name} with function {event_function.name} raised an exception",
                                    level='error', sources=[event_function.plugin_id, self.created_by], exc_info=True).send()

        return args

