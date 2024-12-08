# -*- coding: utf-8 -*-
# Project: bastproxy
# Filename: libs/tracking/types/_trackbase.py
#
# File Description: Holds
#
# By: Bast
"""
Holds a base trackable class
"""
# Standard Library
from uuid import uuid4
from functools import wraps
import datetime
import logging

# 3rd Party

# Project
from ..utils.changelog import ChangeLogEntry

exception_on_lock_error = True

def check_lock(func):
    @wraps(func)
    def wrapper(self, *args, **kwargs):
        if hasattr(self, '_tracking_locked') and self._tracking_locked:
            raise RuntimeError(f"{self.__class__.__name__} is locked and cannot be modified.")
        return func(self, *args, **kwargs)
    return wrapper

def track_changes(method):
    """Decorator to ensure the object is not locked before performing a method and to track changes."""
    @wraps(method)
    def wrapper(self, *args, **kwargs):
        # reset the tracking context
        if self._tracking_is_trackable(self) in ['TrackedDict', 'TrackedList']:
            data_pre_change = repr(self)

        self._tracking_context = {}

        # Call the original method
        result = method(self, *args, **kwargs)

        # Check if the object has a tracking_context attribute (for tracking changes)
        if self._tracking_context and 'action' in self._tracking_context:

            if 'removed_items' in self._tracking_context:
                for olditem in self._tracking_context['removed_items']:
                    if self._tracking_is_trackable(olditem):
                        if olditem._tracking_uuid in self._tracking_child_tracked_items:
                            del self._tracking_child_tracked_items[olditem._tracking_uuid]
                        olditem.tracking_remove_observer(self._tracking_notify_observers)

            if self._tracking_is_trackable(self) in ['TrackedDict', 'TrackedList']:
                self._tracking_context['data_pre_change'] = data_pre_change
                self._tracking_context['data_post_change'] = repr(self)
            self._tracking_context['method'] = method.__name__
            self.tracking_create_change(**self._tracking_context)

        self._tracking_context = {}

        return result

    return wrapper

class TrackBase:
    def __init__(self, tracking_name=None, tracking_auto_converted_in=None, tracking_auto_convert=False,
                 tracking_parent=None, tracking_location=None, tracking_delimiter='+', **kwargs):
        self._tracking_name = tracking_name
        self._tracking_auto_converted_in = tracking_auto_converted_in
        self._tracking_uuid = uuid4().hex
        self._tracking_observers = {}
        self._tracking_context = {}
        self._tracking_changes: list[ChangeLogEntry] = []
        self._tracking_locked = False
        self._tracking_auto_convert = tracking_auto_convert
        self._tracking_created = datetime.datetime.now()
        self._tracking_child_tracked_items = {}
        self._tracking_delimiter = tracking_delimiter
        self._tracking_debug_flag = False
        if tracking_parent:
            tracking_parent._tracking_add_child_tracked_item(tracking_location, self)

        self.tracking_create_change(action='init',
                                    init_data=f"{self}")
        self._tracking_convert_all_values()

    def _tracking_convert_value(self, value, location=None):
        if hasattr(self, '_tracking_auto_convert') and self._tracking_auto_convert:
            value = self._tracking_convert_to_trackable(value,
                                         tracking_auto_converted_in=self._tracking_uuid,
                                         tracking_auto_convert=self._tracking_auto_convert,
                                         tracking_parent=self, tracking_location=location)
        return value

    def _tracking_debug(self, message):
        if self._tracking_debug_flag:
            logging.info(f"{self._tracking_uuid[:4]}..{self._tracking_uuid[-4:]} - {message}")

    def _tracking_add_child_tracked_item(self, location, trackable_item):
        self._tracking_child_tracked_items[trackable_item._tracking_uuid] = {'location':location,
                                                                   'item':trackable_item}
        if self._tracking_locked:
            trackable_item.lock()
        else:
            trackable_item.unlock()
        trackable_item.tracking_add_observer(self._tracking_notify_observers)

    def _tracking_remove_child_tracked_item(self, trackable_item):
        self._tracking_child_tracked_items.pop(trackable_item._tracking_uuid, None)
        trackable_item.tracking_remove_observer(self._tracking_notify_observers)

    def _tracking_convert_all_values(self):
        raise NotImplementedError

    def tracking_add_observer(self, observer, priority=50):
        if priority not in self._tracking_observers:
            self._tracking_observers[priority] = []
        if observer not in self._tracking_observers[priority] and observer != self._tracking_notify_observers:
            self._tracking_observers[priority].append(observer)

    def tracking_remove_observer(self, observer):
        """
        remove an observer
        """
        for priority in self._tracking_observers:
            if observer in self._tracking_observers[priority]:
                self._tracking_observers[priority].remove(observer)

    def _tracking_notify_observers(self, change_log_entry):
        """
        notify all observers
        """
        priority_list = sorted(self._tracking_observers.keys())
        for priority in priority_list:
            for observer in self._tracking_observers[priority]:
                observer(change_log_entry)

    def tracking_add_change(self, change_log_entry):
        """
        add a change log record to the list of changes
        """
        self._tracking_changes.append(change_log_entry)
        self._tracking_changes.sort()

    def tracking_create_change(self, **kwargs):
        """
        create a change log entry for this object
        """
        if 'locked' not in kwargs:
            kwargs['locked'] = self._tracking_locked
        if 'type' not in kwargs:
            kwargs['type'] = self._tracking_is_trackable(self)
        change_log_entry = ChangeLogEntry(self._tracking_uuid,
                                            **kwargs)
        change_log_entry.add_to_tree(self._tracking_format_tree_location(change_log_entry.extra.get('location', None)))
        self._tracking_changes.append(change_log_entry)
        self._tracking_notify_observers(change_log_entry)

    def _tracking_format_tree_location(self, location=None):
        # return {'type': self._tracking_is_trackable(self), 'uuid': self._tracking_uuid, 'location': f"{self._tracking_delimiter}{location}"}
        if location is not None:
            return {'type': self._tracking_is_trackable(self), 'uuid': self._tracking_uuid, 'location': f"{self._tracking_delimiter}{location}"}
        return {'type': self._tracking_is_trackable(self), 'uuid': self._tracking_uuid}

    def lock(self):
        self._tracking_locked = True
        for key in self._tracking_child_tracked_items:
            self._tracking_child_tracked_items[key]['item'].lock()
        self.tracking_create_change(action='lock')

    def unlock(self):
        self._tracking_locked = False
        for key in self._tracking_child_tracked_items:
            self._tracking_child_tracked_items[key]['item'].unlock()
        self.tracking_create_change(action='unlock')

    def tracking_get_formatted_updates(self):
        # return self._tracking_changes[0].format_detailed()

        t_list = []
        for item in self._tracking_changes[:20]:
        # for item in self._tracking_changes:
            t_list.append('--------------------------------------')
            t_list.extend(item.format_detailed())
        t_list.append('--------------------------------------')
        return t_list

    def _tracking_convert_to_trackable(self, obj, tracking_auto_converted_in=None, tracking_auto_convert=False,
                            tracking_parent: 'TrackBase | None' = None, tracking_location=None):
        """
        convert the object to a trackable object
        """
        if isinstance(obj, dict) and not self._tracking_is_trackable(obj):
            from .trackeddict import TrackedDict
            return TrackedDict(obj,
                            tracking_auto_converted_in=tracking_auto_converted_in,
                            tracking_auto_convert=tracking_auto_convert,
                            tracking_parent=tracking_parent, tracking_location=tracking_location)
        if isinstance(obj, list) and not self._tracking_is_trackable(obj):
            from .trackedlist import TrackedList
            return TrackedList(obj,
                            tracking_auto_converted_in=tracking_auto_converted_in,
                            tracking_auto_convert=tracking_auto_convert,
                            tracking_parent=tracking_parent, tracking_location=tracking_location)
        return obj

    def _tracking_is_trackable(self, obj):
        """
        check if the object is trackable
        returns the type of trackable object or False
        """
        from .trackeddict import TrackedDict
        from .trackedlist import TrackedList
        from .trackedattributes import TrackedAttr
        if isinstance(obj, TrackedDict):
            return 'TrackedDict'
        elif isinstance(obj, TrackedList):
            return 'TrackedList'
        elif isinstance(obj, TrackedAttr):
            return 'TrackedAttr'
        return False

    def _tracking_convert_to_untrackable(self, obj):
        """
        convert the object to a normal object
        """
        from ..types.trackeddict import TrackedDict
        from ..types.trackedlist import TrackedList
        if self._tracking_is_trackable(obj):
            if isinstance(obj, TrackedDict):
                return {item: self._tracking_convert_to_untrackable(obj[item]) for item in obj}
            if isinstance(obj, TrackedList):
                return [self._tracking_convert_to_untrackable(item) for item in obj]
        return obj
