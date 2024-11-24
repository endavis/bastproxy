# -*- coding: utf-8 -*-
# Project: bastproxy
# Filename: libs/tracking/utils/attributes.py
#
# File Description: Holds a class that monitors attributes
#
# By: Bast
"""
Holds a class that monitors attributes
"""
# Standard Library
import contextlib
import sys

# 3rd Party

# Project
from ..utils.trackable import is_trackable
from ..types._trackbase import TrackBase

# TODO: create LOCKEDEXCEPTION when trying to update a locked attribute, list, or dict

class TrackedAttributes(TrackBase):
    def __init__(self, tracking_auto_convert=True):
        TrackBase.__init__(self, tracking_auto_convert=tracking_auto_convert)
        self._tracking_attributes_to_monitor = []
        self._tracking_locked_attributes = []
        self._tracking_original_values = {}
        self._tracking_delimiter = '.'

    def _tracking_is_tracking_attribute(self, attribute_name):
        if not hasattr(self, '_tracking_attributes_to_monitor'):
            return False
        return attribute_name in self._tracking_attributes_to_monitor

    def _tracking_is_locked_attribute(self, attribute_name):
        if not hasattr(self, '_tracking_locked_attributes'):
            return False
        return attribute_name in self._tracking_locked_attributes

    def _tracking_notify_observers(self, change_log_entry):
        """
        notify all observers
        """
        if change_log_entry.tracked_item_uuid != self._tracking_uuid:
            for item in self._tracking_attributes_to_monitor:
                value = getattr(self, item)
                if is_trackable(value) and value._tracking_uuid == change_log_entry.tracked_item_uuid:
                    new_change = change_log_entry.copy(change_log_entry.extra['type'], self._tracking_uuid)
                    if 'location' in new_change.extra:
                        new_change.extra['location'] = f'.{item}{value._tracking_delimiter}{new_change.extra['location']}'
                    else:
                        new_change.extra['location'] = f'.{item}'

                    change_log_entry = new_change
                    break

        if change_log_entry not in self._tracking_changes:
            self._tracking_changes.append(change_log_entry)
        super()._tracking_notify_observers(change_log_entry)

    def tracking_add_attribute_to_monitor(self, attribute_name):
        if hasattr(self, attribute_name) and attribute_name not in self._tracking_attributes_to_monitor:
            self._tracking_attributes_to_monitor.append(attribute_name)
            original_value = value = getattr(self, attribute_name)
            value = self._tracking_convert_value(value)
            super().__setattr__(attribute_name, value)
            self.tracking_create_change(action='start monitoring', location=f".{attribute_name}", value=original_value)


    def _tracking_attribute_change(self, method, attribute_name, original_value, new_value):
        if original_value == '#!NotSet':
            with contextlib.suppress(Exception):
                self._tracking_original_values[attribute_name] = new_value
        if original_value not in ["#!NotSet", new_value]:
            extra = {'data_pre_change': original_value, 'data_post_change': new_value}
            self.tracking_create_change(action='update', method=method, location=f".{attribute_name}",
                                     value=new_value,
                                     locked=self._tracking_is_locked_attribute(attribute_name),
                                     **extra)

    def _tracking_convert_all_values(self):
        pass

    def _tracking_get_original_value(self, attribute_name):
        return self._tracking_original_values.get(attribute_name, None)

    def _tracking_lock_attribute(self, attribute_name):
        self._tracking_locked_attributes.append(attribute_name)

    def _tracking_unlock_attribute(self, attribute_name):
        self._tracking_locked_attributes.remove(attribute_name)

    def __setattr__(self, attribute_name, value):
        if not(self._tracking_is_locked_attribute(attribute_name) or (hasattr(self, '_tracking_locked') and self._tracking_locked)):
            try:
                original_value = getattr(self, attribute_name)
            except AttributeError:
                original_value = '#!NotSet'
            if self._tracking_is_tracking_attribute(attribute_name):
                value = self._tracking_convert_value(value)
            super().__setattr__(attribute_name, value)

        self._tracking_attribute_change(sys._getframe().f_code.co_name, attribute_name, original_value, value)
