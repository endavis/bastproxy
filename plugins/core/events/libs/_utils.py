# Project: bastproxy
# Filename: plugins/core/events/_utils.py
#
# File Description: Holds the decorator for registering to events
#
# By: Bast
"""

"""
# Standard Library

# 3rd Party

# Project

CANRELOAD = False

class RegisterToEvent:
    """
    a class to decorate a function to register it to an event
    """
    def __init__(self, **kwargs):
        """
        kwargs:
            event_name: the event to register to
            priority: the priority to register the function with (Default: 50)
        """
        self.registration_args = {'event_name':'', 'priority':50} | kwargs

    def __call__(self, func):
        if not hasattr(func, 'event_registration'):
            func.event_registration = []
        func.event_registration.append(self.registration_args)

        return func
