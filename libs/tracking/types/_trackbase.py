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
import datetime

# 3rd Party

# Project
from ..utils.changelog import ChangeLogEntry
from ..utils.trackable import is_trackable, convert_to_trackable

class TrackBase:
    def __init__(self, tracking_name=None, tracking_auto_converted_in=None, tracking_auto_convert=False,
                 tracking_delimiter='+', **kwargs):
        self._tracking_name = tracking_name
        self._tracking_auto_converted_in = tracking_auto_converted_in
        self._tracking_uuid = uuid4().hex
        self._tracking_observers = {}
        self._tracking_changes: list[ChangeLogEntry] = []
        self._tracking_locked = False
        self._tracking_auto_convert = tracking_auto_convert
        self._tracking_created = datetime.datetime.now()
        self._tracking_child_tracked_items = {}
        self._tracking_delimiter = tracking_delimiter
        self._tracking_debug_flag = False

        ChangeLogEntry(self._tracking_uuid, type=is_trackable(self), name=self._tracking_name,
                       action='init', locked=self._tracking_locked,
                       related_uuid=self._tracking_auto_converted_in)
        self._tracking_convert_all_values()

    def _tracking_convert_value(self, value):
        if hasattr(self, '_tracking_auto_convert') and self._tracking_auto_convert:
            value = convert_to_trackable(value,
                                         tracking_auto_converted_in=self._tracking_uuid,
                                         tracking_auto_convert=self._tracking_auto_convert)
            if is_trackable(value):
                value.tracking_add_observer(self._tracking_notify_observers)
        return value

    def _tracking_debug(self, message):
        if self._tracking_debug_flag:
            logging.info(f"{self._tracking_name} - {message}")

    def _tracking_add_child_tracked_item(self, location, trackable_item):
        self._tracking_child_tracked_items[trackable_item._tracking_uuid] = {'location':location,
                                                                   'item':trackable_item}
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
            kwargs['type'] = is_trackable(self)
        change_log_entry = ChangeLogEntry(self._tracking_uuid,
                                            **kwargs)
        self._tracking_changes.append(change_log_entry)
        self._tracking_notify_observers(change_log_entry)

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
