# -*- coding: utf-8 -*-
# Project: bastproxy
# Filename: libs/tracking/utils/changelog.py
#
# File Description: Holds a class that monitors attributes
#
# By: Bast
"""
Holds a class that monitors attributes
"""
# Standard Library
import typing

# 3rd Party

# Project
if typing.TYPE_CHECKING:
    from ..types._trackbase import TrackBase

def is_trackable(obj):
    """
    check if the object is trackable
    returns the type of trackable object or False
    """
    from ..types.trackeddict import TrackedDict
    from ..types.trackedlist import TrackedList
    from ..types.trackedattributes import TrackedAttributes
    if isinstance(obj, TrackedDict):
        return 'TrackedDict'
    elif isinstance(obj, TrackedList):
        return 'TrackedList'
    elif isinstance(obj, TrackedAttributes):
        return 'TrackedAttributes'
    return False

def convert_to_trackable(obj, tracking_auto_converted_in=None, tracking_auto_convert=False,
                         tracking_parent: 'TrackBase | None' = None, tracking_location=None):
    """
    convert the object to a trackable object
    """
    from ..types.trackeddict import TrackedDict
    from ..types.trackedlist import TrackedList
    if isinstance(obj, dict):
        return TrackedDict(obj,
                           tracking_auto_converted_in=tracking_auto_converted_in,
                           tracking_auto_convert=tracking_auto_convert,
                           tracking_parent=tracking_parent, tracking_location=tracking_location)
    if isinstance(obj, list):
        return TrackedList(obj,
                           tracking_auto_converted_in=tracking_auto_converted_in,
                           tracking_auto_convert=tracking_auto_convert,
                           tracking_parent=tracking_parent, tracking_location=tracking_location)
    return obj

def convert_to_untrackable(obj):
    """
    convert the object to a normal object
    """
    from ..types.trackeddict import TrackedDict
    from ..types.trackedlist import TrackedList
    if is_trackable(obj):
        if isinstance(obj, TrackedDict):
            return {item: convert_to_untrackable(obj[item]) for item in obj}
        if isinstance(obj, TrackedList):
            return [convert_to_untrackable(item) for item in obj]
    return obj
