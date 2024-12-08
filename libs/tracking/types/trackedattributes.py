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
from ..types._trackbase import TrackBase, track_changes, check_lock

# TODO: create LOCKEDEXCEPTION when trying to update a locked attribute, list, or dict

class TrackedAttributes(TrackBase):
    def __init__(self, tracking_auto_convert=True,
                 tracking_parent=None, tracking_location=None):
        TrackBase.__init__(self, tracking_auto_convert=tracking_auto_convert,
                           tracking_parent=tracking_parent, tracking_location=tracking_location,
                           tracking_delimiter='.')
        self._tracking_attributes_to_monitor = []
        self._tracking_locked_attributes = []
        self._tracking_original_values = {}

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
                if self._tracking_is_trackable(value) and value._tracking_uuid == change_log_entry.tracked_item_uuid:
                    new_change = change_log_entry.copy(change_log_entry.extra['type'], self._tracking_uuid)
                    new_change.add_to_tree(self._tracking_format_tree_location(item))
                    if 'location' in new_change.extra:
                        new_change.extra['location'] = f'{item}{value._tracking_delimiter}{new_change.extra['location']}'
                    else:
                        new_change.extra['location'] = f'{item}'

                    change_log_entry = new_change

                    break

        if change_log_entry not in self._tracking_changes:
            self._tracking_changes.append(change_log_entry)
        super()._tracking_notify_observers(change_log_entry)

    def tracking_add_attribute_to_monitor(self, attribute_name):
        if hasattr(self, attribute_name) and attribute_name not in self._tracking_attributes_to_monitor:
            self._tracking_attributes_to_monitor.append(attribute_name)
            original_value = value = getattr(self, attribute_name)
            value = self._tracking_convert_value(value, attribute_name)
            super().__setattr__(attribute_name, value)
            self.tracking_create_change(action='start monitoring', location=f"{attribute_name}", value=original_value)

    def _tracking_attribute_change(self, method, attribute_name, original_value, new_value):
        if original_value == '#!NotSet':
            with contextlib.suppress(Exception):
                self._tracking_original_values[attribute_name] = new_value
        if original_value not in ["#!NotSet", new_value]:
            extra = {'data_pre_change': original_value, 'data_post_change': getattr(self, attribute_name)}
            self.tracking_create_change(action='update', method=method, location=f"{attribute_name}",
                                     value=new_value,
                                     attribute_locked=self._tracking_is_locked_attribute(attribute_name),
                                     **extra)

    def _tracking_convert_all_values(self):
        pass

    def _tracking_get_original_value(self, attribute_name):
        return self._tracking_original_values.get(attribute_name, None)

    @track_changes
    def _tracking_lock_attribute(self, attribute_name):
        if not hasattr(self, attribute_name):
            return

        self._tracking_locked_attributes.append(attribute_name)
        value = getattr(self, attribute_name)
        if self._tracking_is_trackable(value):
            value.lock()

        self._tracking_context['action'] = 'lock'
        self._tracking_context['attribute_name'] = attribute_name
        self._tracking_context['attribute_locked'] = self._tracking_is_locked_attribute(attribute_name)

    def _tracking_unlock_attribute(self, attribute_name):
        if not hasattr(self, attribute_name):
            return

        if attribute_name in self._tracking_locked_attributes:
            value = getattr(self, attribute_name)
            if self._tracking_is_trackable(value):
                value.unlock()

            self._tracking_locked_attributes.remove(attribute_name)
            self.tracking_create_change(action='unlock', attribute_name=attribute_name,
                                        attribute_locked=self._tracking_is_locked_attribute(attribute_name))

    @track_changes
    def lock(self, attribute_name=None):
        if attribute_name:
            self._tracking_lock_attribute(attribute_name)
        else:
            for attribute in self._tracking_attributes_to_monitor:
                self._tracking_lock_attribute(attribute)
            self._tracking_locked = True

            # self.tracking_create_change(action='lock')
            self._tracking_context['action'] = 'lock'

    def unlock(self, attribute_name=None):
        if attribute_name:
            self._tracking_unlock_attribute(attribute_name)
        else:
            self._tracking_locked = False
            for attribute in self._tracking_attributes_to_monitor:
                self._tracking_unlock_attribute(attribute)

            self.tracking_create_change(action='unlock')

    def __setattr__(self, attribute_name, value):
        if self._tracking_is_locked_attribute(attribute_name):
            raise RuntimeError(f"{self.__class__.__name__}.{attribute_name} is locked and cannot be modified.")

        try:
            original_value = getattr(self, attribute_name)
        except AttributeError:
            original_value = '#!NotSet'

        if not self._tracking_is_tracking_attribute(attribute_name) \
           or not(self._tracking_is_locked_attribute(attribute_name)) \
           and (hasattr(self, '_tracking_locked') and not self._tracking_locked):
            if self._tracking_is_tracking_attribute(attribute_name):
                value = self._tracking_convert_value(value, attribute_name)
            super().__setattr__(attribute_name, value)

        if self._tracking_is_tracking_attribute(attribute_name):
            self._tracking_attribute_change(sys._getframe().f_code.co_name, attribute_name, original_value, value)

    def _tracking_known_uuids_tree(self, level=0, attribute_name=None, emptybar=None):
        if emptybar is None:
            emptybar = {}
        known_uuids = []
        if level == 0:
            emptybar[level] = True
            known_uuids.append(f"{self._tracking_is_trackable(self)}:{self._tracking_uuid}")
            level += 1
        if attribute_name:
            emptybar[level] = True
            pre_string = ''.join('    ' if emptybar[i] else ' |  ' for i in range(level))
            value = getattr(self, attribute_name)
            known_uuids.append(f"{pre_string} |-> " \
                               f"Location: {attribute_name} Item: {self._tracking_is_trackable(value)}:{value._tracking_uuid}")
            known_uuids.extend(value._tracking_known_uuids_tree(level + 1, emptybar=emptybar))
        else:
            emptybar[level] = False
            left = self._tracking_attributes_to_monitor[:]
            pre_string = ''.join('    ' if emptybar[i] else ' |  ' for i in range(level))
            for attribute_name in self._tracking_attributes_to_monitor:
                left.remove(attribute_name)
                if not left:
                    emptybar[level] = True
                value = getattr(self, attribute_name)
                if self._tracking_is_trackable(value):
                    known_uuids.append(f"{pre_string} |-> " \
                                       f"Location: {attribute_name} Item: {self._tracking_is_trackable(value)}:{value._tracking_uuid}")
                    known_uuids.extend(value._tracking_known_uuids_tree(level + 1, emptybar=emptybar))
        return known_uuids

    def _tracking_format_tree_location(self, location=None):
        if location is not None:
            return {'type': self._tracking_is_trackable(self), 'uuid': self._tracking_uuid, 'location': f".{location}"}
        return {'type': self._tracking_is_trackable(self), 'uuid': self._tracking_uuid}
        # if location is not None:
        #     return f"{self._tracking_is_trackable(self)}({self._tracking_uuid}).{location}"
        # return f"{self._tracking_is_trackable(self)}({self._tracking_uuid})"
