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
import typing

# 3rd Party

# Project
from libs.api import API

class Callback: # pylint: disable=too-few-public-methods
    """
    a basic callback class
    """
    def __init__(self, name: str, owner_id: str, func: typing.Callable, enabled: bool=True):
        """
        init the class
        """
        self.name: str = name
        self.owner_id: str = owner_id if owner_id else f"{owner_id}:callback:{name}"
        self.api = API(owner_id=self.owner_id)
        self.raised_count: int = 0
        self.func: typing.Callable = func
        self.enabled: bool = enabled
        self.created_time: datetime.datetime = datetime.datetime.now(datetime.timezone.utc)
        self.last_raised_datetime: datetime.datetime | None = None

    def execute(self, args: dict | None = None):
        """
        execute the callback
        """
        self.last_raised_datetime = datetime.datetime.now(datetime.timezone.utc)
        self.raised_count = self.raised_count + 1
        if args:
            return self.func(args)
        else:
            return self.func()

    def __str__(self) -> str:
        """
        return a string representation of the callback
        """
        return f"Event {self.name:<10} : {self.owner_id:<15}"

    def __eq__(self, other_function: typing.Callable) -> bool:
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
