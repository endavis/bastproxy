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

class TrackedDict(TrackBase, dict):
    def __init__(self, *args, tracking_auto_converted_in=None, tracking_auto_convert=False,
                 tracking_parent=None, tracking_location=None, **kwargs):
        dict.__init__(self, *args, **kwargs)
        TrackBase.__init__(self, tracking_auto_converted_in=tracking_auto_converted_in,
                           tracking_auto_convert=tracking_auto_convert,
                           tracking_parent=tracking_parent, tracking_location=tracking_location,
                           tracking_delimiter=':')

    def _tracking_convert_all_values(self):
        for key, value in self.items():
            self[key] = self._tracking_convert_value(value, key)

    def _tracking_notify_observers(self, change_log_entry):
        """
        notify all observers
        """
        if change_log_entry.tracked_item_uuid != self._tracking_uuid and change_log_entry.tracked_item_uuid in self._tracking_child_tracked_items:
            new_change = change_log_entry.copy(change_log_entry.extra['type'], self._tracking_uuid)
            new_change.add_to_tree(self._tracking_format_tree_location(self._tracking_child_tracked_items[change_log_entry.tracked_item_uuid]["location"]))

            if 'location' in new_change.extra:
                delimiter = self._tracking_child_tracked_items[change_log_entry.tracked_item_uuid]['item']._tracking_delimiter
                new_change.extra['location'] = f'{self._tracking_child_tracked_items[change_log_entry.tracked_item_uuid]["location"]}{delimiter}{new_change.extra['location']}'
            else:
                new_change.extra['location'] = f'{self._tracking_child_tracked_items[change_log_entry.tracked_item_uuid]["location"]}'

            change_log_entry = new_change

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
            value = self._tracking_convert_value(value, key)
            super().__setitem__(key, value)

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

    def popitem(self):
        extra = {'data_pre_change': repr(self)}

        key, value = None, None

        if not self._tracking_locked:
            key, value = super().popitem()
            if is_trackable(value):
                self._tracking_remove_child_tracked_item(value)

        extra['data_post_change'] = repr(self)
        self.tracking_create_change(action='remove', method=sys._getframe().f_code.co_name,
                                    location=key, value=value, **extra)

        return key, value

    def update(self, *args, **kwargs):
        extra = {'data_pre_change': repr(self)}

        if not self._tracking_locked:
            new_dict = {}
            for key, value in dict(*args, **kwargs).items():
                new_dict[key] = self._tracking_convert_value(value, key)
            super().update(new_dict)

        extra['data_post_change'] = repr(self)
        self.tracking_create_change(action='update', method=sys._getframe().f_code.co_name,
                                    **extra, value=new_dict)

    def setdefault(self, key, default=None):
        extra = {'data_pre_change': repr(self)}
        original_default = default

        if not self._tracking_locked:
            if key not in self:
                default = self._tracking_convert_value(default, key)
            default = super().setdefault(key, default)

        extra['data_post_change'] = repr(self)
        self.tracking_create_change(action='update', method=sys._getframe().f_code.co_name,
                                    location=key, default=original_default,
                                    return_value=default, **extra)
        return default

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
        new_dict = self._tracking_convert_to_untrackable(self) if untracked else super().copy()
        self.tracking_create_change(action='copy', method=sys._getframe().f_code.co_name)
        return new_dict

    def _tracking_known_uuids_tree(self, level=0, emptybar=None):
        if emptybar is None:
            emptybar = {}
        known_uuids = []
        if level == 0:
            emptybar[level] = True
            known_uuids.append(f"{self._tracking_is_trackable(self)}:{self._tracking_uuid}")
            level += 1
        emptybar[level] = False
        pre_string = ''.join('    ' if emptybar[i] else ' |  ' for i in range(level))
        self._tracking_known_uuids_tree_helper(known_uuids, emptybar, level, pre_string)
        return known_uuids

    def _tracking_known_uuids_tree_helper(self, known_uuids, emptybar, level, pre_string):
        left = list(self.keys())
        for key in self:
            left.remove(key)
            if not left:
                emptybar[level] = True
            if self._tracking_is_trackable(self[key]):
                known_uuids.append(f"{pre_string} |-> " \
                                   f"Location: ['{key}'] Item: {self._tracking_is_trackable(self[key])}:{self[key]._tracking_uuid}")
                known_uuids.extend(self[key]._tracking_known_uuids_tree(level + 1, emptybar=emptybar))

    def __ior__(self, other):
        """
        don't implement this because it creates
        a new dict instead of updating the current one
        and tracking information is lost
        """
        raise NotImplementedError('The |= operator is not supported for TrackedDict')

    def _tracking_format_tree_location(self, location=None):
        if location is not None:
            return {'type': self._tracking_is_trackable(self), 'uuid': self._tracking_uuid, 'location': f"[{repr(location)}]"}
        return {'type': self._tracking_is_trackable(self), 'uuid': self._tracking_uuid}
