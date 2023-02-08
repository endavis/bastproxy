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

# 3rd Party

# Project

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
        return f"Event {self.name:<10} : {self.plugin:<15}"
