# -*- coding: utf-8 -*-
# Project: bastproxy
# Filename: libs/callback.py
#
# File Description: a class to track callbacks
#
# By: Bast
"""
This plugin is used to track callbacks
"""
# Standard Library
import datetime

# 3rd Party

# Project
from libs.api import API

class Callback: # pylint: disable=too-few-public-methods
    """
    a basic callback class
    """
    def __init__(self, name, plugin_id, func, enabled=True):
        """
        init the class
        """
        self.api = API()
        self.name = name
        self.plugin_id = plugin_id
        self.raised_count = 0
        self.func = func
        self.enabled = enabled
        self.created_time = datetime.datetime.now(datetime.timezone.utc)
        self.last_raised_datetime = None

    def execute(self, args=None):
        """
        execute the callback
        """
        self.last_raised_datetime = datetime.datetime.now(datetime.timezone.utc)
        self.raised_count = self.raised_count + 1
        if args:
            self.func(args)
        else:
            self.func()

    def __str__(self):
        """
        return a string representation of the callback
        """
        return f"Event {self.name:<10} : {self.plugin_id:<15}"

    def __eq__(self, other_function):
        """
        check equality between two functions
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
