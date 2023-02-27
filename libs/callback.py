# -*- coding: utf-8 -*-
# Project: bastproxy
# Filename: libs/event.py
#
# File Description: a basic event class
#
# By: Bast
"""
This plugin has the base event class
"""
# Standard Library
import datetime

# 3rd Party

# Project
from libs.api import API

class Callback: # pylint: disable=too-few-public-methods
    """
    a basic event class
    """
    def __init__(self, name, plugin_id, func, enabled=True):
        """
        init the class
        """
        self.api = API()
        self.name = name
        self.plugin_id = plugin_id
        self.fired_count = 0
        self.func = func
        self.enabled = enabled
        self.created_time = datetime.datetime.now(datetime.timezone.utc)
        self.last_fired_datetime = None

    def execute(self):
        """
        execute the event
        """
        self.last_fired_datetime = datetime.datetime.now(datetime.timezone.utc)
        self.fired_count = self.fired_count + 1
        self.func()

    def __str__(self):
        """
        return a string representation of the timer
        """
        return f"Event {self.name:<10} : {self.plugin_id:<15}"

    def __eq__(self, other_function):
        """
        check equality between two event functions
        """
        if callable(other_function):
            if other_function == self.func:
                return True
        try:
            if self.func == other_function.func:
                return True
        except AttributeError:
            return False

        return False
