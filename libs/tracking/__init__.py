# -*- coding: utf-8 -*-
# Project: bastproxy
# Filename: libs/records/__init__.py
#
# File Description: a "package" to manage records
#
# By: Bast
"""
This "package"" has classes for various trackable objects

The main one will be the class AttributeMonitor,
which will monitor the attributes of an object as well
as convert lists and dicts to TrackedList and TrackedDict
"""

__all__ = ['AttributeMonitor', 'TrackedDict', 'TrackedList',
           'TrackedAttr', 'ChangeLogEntry',
           'add_to_ignore_in_stack']

from .types._trackbase import TrackBase
from .types.trackeddict import TrackedDict
from .types.trackedlist import TrackedList
from .types.trackedattributes import TrackedAttr
from .utils.attributes import AttributeMonitor
from .utils.changelog import ChangeLogEntry

from .utils.changelog import add_to_ignore_in_stack