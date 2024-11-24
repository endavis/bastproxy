# -*- coding: utf-8 -*-
# Project: bastproxy
# Filename: libs/records/rtypes/__init__.py
#
# File Description: Holds the base record type
#
# By: Bast
"""
Holds the base record type
"""
# Standard Library
import sys

# 3rd Party

# Project
from ..utils.trackable import is_trackable, convert_to_untrackable
from ._trackbase import TrackBase

# TODO: overload copy, popitem, update, setdefault

class TrackedDict(TrackBase, dict):
    def __init__(self, *args, tracking_auto_converted_in=None, tracking_auto_convert=False, **kwargs):
        dict.__init__(self, *args, **kwargs)
        TrackBase.__init__(self, tracking_auto_converted_in=tracking_auto_converted_in,
                           tracking_auto_convert=tracking_auto_convert)
        self._tracking_delimiter = ':'

    def _tracking_convert_all_values(self):
        for key, value in self.items():
            self[key] = self._tracking_convert_value(value)

    def _tracking_notify_observers(self, change_log_entry):
        """
        notify all observers
        """
        if change_log_entry.tracked_item_uuid != self._tracking_uuid and change_log_entry.tracked_item_uuid in self._tracking_child_tracked_items:
            new_change = change_log_entry.copy(change_log_entry.extra['type'], self._tracking_uuid)
            if 'location' in new_change.extra:
                delimiter = self._tracking_child_tracked_items[change_log_entry.tracked_item_uuid]['item']._tracking_delimiter
                new_change.extra['location'] = f'{self._tracking_child_tracked_items[change_log_entry.tracked_item_uuid]["location"]}{delimiter}{new_change.extra['location']}'
            else:
                new_change.extra['location'] = f'.{self._tracking_child_tracked_items[change_log_entry.tracked_item_uuid]["location"]}'

            change_log_entry = new_change
            change_log_entry.add_to_tree(f"{is_trackable(self)}:{self._tracking_uuid}")

        if change_log_entry not in self._tracking_changes:
            self._tracking_changes.append(change_log_entry)
        super()._tracking_notify_observers(change_log_entry)

    def __delitem__(self, key) -> None:
        extra = {'data_pre_change': repr(self)}

        if not self._tracking_locked:
            old_item = self[key]
            super().__delitem__(key)
            if is_trackable(old_item):
                self._tracking_remove_child_tracked_item(old_item)

        extra['data_post_change'] = repr(self)
        self.tracking_create_change(action='remove', method=sys._getframe().f_code.co_name,
                                          location=key, **extra)

    def __setitem__(self, key, value) -> None:
        extra = {'data_pre_change': repr(self)}
        action = 'update' if key in self else 'add'
        if not self._tracking_locked:
            value = self._tracking_convert_value(value)
            super().__setitem__(key, value)
            if is_trackable(value):
                self._tracking_add_child_tracked_item(key, value)

        extra['data_post_change'] = repr(self)
        self.tracking_create_change(action=action, method=sys._getframe().f_code.co_name, location=key,
                                          value=value, **extra)

    def pop(self, key, default=None):
        extra = {'data_pre_change': repr(self)}

        if not self._tracking_locked:
            old_item = self[key]
            value = super().pop(key, default)
            if is_trackable(old_item):
                self._tracking_remove_child_tracked_item(old_item)

        extra['data_post_change'] = repr(self)
        self.tracking_create_change(action='remove', method=sys._getframe().f_code.co_name,
                                    location=key, value=value, **extra)

    def clear(self):
        """
        clear the list
        """
        extra = {'data_pre_change': repr(self)}

        if not self._tracking_locked:
            extra['data_pre_change'] = repr(self)
            for key in self:
                if is_trackable(self[key]):
                    self._tracking_remove_child_tracked_item(self[key])

            super().clear()

        extra['data_post_change'] = repr(self)
        self.tracking_create_change(action='remove', method=sys._getframe().f_code.co_name,
                                    **extra)

    def copy(self, untracked=True):
        """
        copy the dict
        """
        new_dict = convert_to_untrackable(self) if untracked else super().copy()
        self.tracking_create_change(action='copy', method=sys._getframe().f_code.co_name)
        return new_dict
