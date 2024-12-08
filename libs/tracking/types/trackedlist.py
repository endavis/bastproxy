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
from ._trackbase import TrackBase, track_changes, check_lock

class TrackedList(TrackBase, list):
    """
    this is a Userlist whose updates are tracked

    callback will take 3 args:
        1. the name of the tracked list
        2. the action for the update
             setitem, insert, append, extend
        3. the position of the update
        4. the value of the update
        5. the lock flag
    """
    def __init__(self, data: list | None = None,
                 tracking_auto_converted_in=None, tracking_auto_convert=False,
                 tracking_parent=None, tracking_location=None):
        """
        initialize the class
        """
        if data is None:
            data = []
        list.__init__(self, data)
        TrackBase.__init__(self,
                           tracking_auto_converted_in=tracking_auto_converted_in,
                           tracking_auto_convert=tracking_auto_convert,
                           tracking_parent=tracking_parent, tracking_location=tracking_location,
                           tracking_delimiter='|')

    def _tracking_convert_all_values(self):
        for index, value in enumerate(self):
            self[index] = self._tracking_convert_value(value, index)

    def _tracking_notify_observers(self, change_log_entry):
        """
        notify all observers
        """
        if change_log_entry.tracked_item_uuid != self._tracking_uuid and change_log_entry.tracked_item_uuid in self._tracking_child_tracked_items:
            new_change = change_log_entry.copy(change_log_entry.extra['type'], self._tracking_uuid)
            # new_change.add_to_tree(f"{self._tracking_is_trackable(self)}({self._tracking_uuid}) {self._tracking_delimiter} {self._tracking_child_tracked_items[change_log_entry.tracked_item_uuid]["location"]}")
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

    @check_lock
    @track_changes
    def __setitem__(self, index : int, item):
        """
        set the item
        """
        if not isinstance(index, int):
            raise TypeError(f"Tracked list index must be an int, not {type(index)}")

        try:
            old_item = self[index]
        except IndexError:
            old_item = None

        item = self._tracking_convert_value(item, index)
        if not self._tracking_locked:
            super().__setitem__(index, item)

        if old_item:
            self._tracking_context.setdefault('removed_items', []).append(old_item)
        self._tracking_context['action'] = 'update'
        self._tracking_context['value'] = item
        self._tracking_context['location'] = index

    @check_lock
    @track_changes
    def __delitem__(self, index: int) -> None:
        """
        delete an item
        """
        if not isinstance(index, int):
            raise TypeError(f"Tracked list index must be an int, not {type(index)}")

        old_item = self[index]
        if not self._tracking_locked:
            super().__delitem__(index)

        self._tracking_context.setdefault('removed_items', []).append(old_item)
        self._tracking_context['action'] = 'update'
        self._tracking_context['value'] = old_item
        self._tracking_context['location'] = index

    @check_lock
    @track_changes
    def append(self, item):
        """
        append an item
        """
        index = 'none'

        if not self._tracking_locked:
            index = len(self)
            item = self._tracking_convert_value(item, index)
            super().append(item)

        self._tracking_context['action'] = 'add'
        self._tracking_context['value'] = item
        self._tracking_context['location'] = index

    @check_lock
    @track_changes
    def extend(self, items: list):
        """
        extend the list
        """
        if not self._tracking_locked:
            new_list = []
            count = len(self)
            for item in items:
                new_item = self._tracking_convert_value(item, count)
                new_list.append(new_item)
                count += 1
            super().extend(new_list)
        else:
            new_list = items

        extend_length = len(new_list)
        current_leng = len(self)

        locations = [str(i - 1) for i in range(current_leng - 1, current_leng - 1 + extend_length)]
        location = ','.join(locations)

        self._tracking_context['action'] = 'add'
        self._tracking_context['value'] = items
        self._tracking_context['location'] = location

    @check_lock
    @track_changes
    def insert(self, index, item):
        """
        insert an item
        """
        if not self._tracking_locked:
            item = self._tracking_convert_value(item, index)
            super().insert(index, item)

        self._tracking_context['action'] = 'add'
        self._tracking_context['value'] = item
        self._tracking_context['location'] = index

    @check_lock
    @track_changes
    def remove(self, item):
        """
        remove an item
        """
        try:
            index = super().index(item)
        except ValueError:
            index = None

        if not self._tracking_locked:
            super().remove(item)

        if index:
            self._tracking_context.setdefault('removed_items', []).append(item)

        self._tracking_context['action'] = 'remove'
        self._tracking_context['value'] = item
        self._tracking_context['location'] = index

    @check_lock
    @track_changes
    def pop(self, index=-1):
        """
        pop an item
        """
        passed_index = index
        actual_index = index

        if passed_index == -1:
            actual_index = len(self) - 1

        item = '###^$^@$^$default###^$^@$^'
        if not self._tracking_locked:
            item = super().pop(index)

        if item != '###^$^@$^$default###^$^@$^':
            self._tracking_context.setdefault('removed_items', []).append(item)
        self._tracking_context['action'] = 'remove'
        self._tracking_context['value'] = None if item == '###^$^@$^$default###^$^@$^' else item
        self._tracking_context['location'] = actual_index
        self._tracking_context['passed_index'] = passed_index

        return item

    @check_lock
    @track_changes
    def clear(self):
        """
        clear the list
        """
        if not self._tracking_locked:
            for item in self:
                self._tracking_context.setdefault('removed_items', []).append(item)

            super().clear()

        self._tracking_context['action'] = 'remove'

    @check_lock
    @track_changes
    def sort(self, key=None, reverse=False):
        """
        sort the list
        """
        if not self._tracking_locked:
            super().sort(key=key, reverse=reverse)
            for item in self._tracking_child_tracked_items:
                self._tracking_child_tracked_items[item]['index'] = self.index(item)

        self._tracking_context['action'] = 'update'

    @check_lock
    @track_changes
    def reverse(self):
        """
        reverse the list
        """
        if not self._tracking_locked:
            super().reverse()
            for item in self._tracking_child_tracked_items:
                self._tracking_child_tracked_items[item]['index'] = self.index(item)

        self._tracking_context['action'] = 'update'

    @check_lock
    @track_changes
    def copy(self, untracked=True):
        """
        copy the list
        """
        new_list = self._tracking_convert_to_untrackable(self) if untracked else super().copy()
        self._tracking_context['action'] = 'copy'
        return new_list

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
        left = list(range(len(self)))
        for item in self:
            left.remove(self.index(item))
            if not left:
                emptybar[level] = True
            if self._tracking_is_trackable(item):
                known_uuids.append(f"{pre_string} |-> " \
                             f"Location: [{self.index(item)}] Item: {self._tracking_is_trackable(item)}:{item._tracking_uuid}")
                known_uuids.extend(item._tracking_known_uuids_tree(level + 1, emptybar=emptybar))

    def _tracking_format_tree_location(self, location=None):
        if location is not None:
            return {'type': self._tracking_is_trackable(self), 'uuid': self._tracking_uuid, 'location': f"[{repr(location)}]"}
        return {'type': self._tracking_is_trackable(self), 'uuid': self._tracking_uuid}

