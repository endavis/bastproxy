# -*- coding: utf-8 -*-
# Project: bastproxy
# Filename: plugins/core/apihelp.py
#
# File Description: a plugin to show api functions and details
#
# By: Bast
"""
This plugin has the base event class
"""
class Event(object): # pylint: disable=too-few-public-methods
    """
    a basic event class
    """
    def __init__(self, name, plugin, func):
        """
        init the class
        """
        self.name = name
        self.plugin = plugin
        self.fired_count = 0
        self.func = func

    def execute(self):
        """
        execute the event
        """
        self.fired_count = self.fired_count + 1
        self.func()

    def __str__(self):
        """
        return a string representation of the timer
        """
        return 'Event %-10s : %-15s' % (self.name, self.plugin)
