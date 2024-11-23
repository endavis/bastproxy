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
from collections import UserList
import sys

# 3rd Party

# Project
from ..utils.trackable import is_trackable, convert_to_untrackable
from ._trackbase import TrackBase

class TrackedList(TrackBase, UserList):
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
                 tracking_auto_converted_in=None, tracking_auto_convert=False):
        """
        initialize the class
        """
        if data is None:
            data = []
        UserList.__init__(self, data)
        TrackBase.__init__(self,
                           tracking_auto_converted_in=tracking_auto_converted_in,
                           tracking_auto_convert=tracking_auto_convert)
        self._tracking_delimiter = '|'

    def _tracking_convert_all_values(self):
        for index, value in enumerate(self):
            self[index] = self._tracking_convert_value(value)

    def _tracking_notify_observers(self, change_log_entry):
        """
        notify all observers
        """
        if change_log_entry.tracked_item_uuid != self._tracking_uuid and change_log_entry.tracked_item_uuid in self._tracking_child_tracked_items:
            new_change = change_log_entry.copy(change_log_entry.type, self._tracking_uuid)
            delimiter = self._tracking_child_tracked_items[change_log_entry.tracked_item_uuid]['item']._tracking_delimiter
            new_change.location = f'{self._tracking_child_tracked_items[change_log_entry.tracked_item_uuid]["location"]}{delimiter}{new_change.location}'
            change_log_entry = new_change

        if change_log_entry not in self._tracking_changes:
            self._tracking_changes.append(change_log_entry)
        super()._tracking_notify_observers(change_log_entry)

    def __setitem__(self, index : int, item):
        """
        set the item
        """
        if not isinstance(index, int):
            raise TypeError(f"Tracked list index must be an int, not {type(index)}")
        extra = {'data_pre_change': repr(self)}

        # TODO: figure out how to handle slices
        if not self._tracking_locked:
            olditem = self[index]
            item = self._tracking_convert_value(item)
            super().__setitem__(index, item)
            if is_trackable(item):
                self._tracking_child_tracked_items[item._tracking_uuid] = {'index':index, 'item':item}
                item.tracking_add_observer(self._tracking_notify_observers)
            if is_trackable(olditem):
                    # ChangeLogEntry(is_trackable(olditem), olditem._tracking_uuid,
                    #             action='removed', removed_from=self.__class__.__name__,
                    #             method='setitem',
                    #             item=index, related_uuid=self._tracking_uuid)
                    if olditem._tracking_uuid in self._tracking_child_tracked_items:
                        del self._tracking_child_tracked_items[olditem._tracking_uuid]
                    olditem.tracking_remove_observer(self._tracking_notify_observers)

        extra['data_post_change'] = repr(self)
        self.tracking_create_change(action='update', method=sys._getframe().f_code.co_name,
                                          location=index, value=item, **extra)

    def __delitem__(self, index: int) -> None:
        """
        delete an item
        """
        extra = {'data_pre_change': repr(self)}

        if not isinstance(index, int):
            raise TypeError(f"Tracked list index must be an int, not {type(index)}")

        # TODO: figure out how to handle slices
        orig_item = self[index]
        if not self._tracking_locked:
            super().__delitem__(index)
            if is_trackable(orig_item):
                self._tracking_remove_child_tracked_item(orig_item)

        extra['data_post_change'] = repr(self)
        self.tracking_create_change(action='remove', method=sys._getframe().f_code.co_name,
                                          location=index, value=orig_item, **extra)

    def append(self, item):
        """
        append an item
        """
        index = 'none'
        extra = {'data_pre_change': repr(self)}

        if not self._tracking_locked:
            item = self._tracking_convert_value(item)
            super().append(item)
            index = self.index(item)
            if is_trackable(item):
                self._tracking_add_child_tracked_item(self.index(item), item)

        extra['data_post_change'] = repr(self)
        self.tracking_create_change(action='add', method=sys._getframe().f_code.co_name,
                                          location=index, value=item, **extra)

    def extend(self, items: list):
        """
        extend the list
        """
        extra = {'data_pre_change': repr(self)}

        if not self._tracking_locked:
            new_list = []
            count = len(self)
            for item in items:
                new_item = self._tracking_convert_value(item)
                new_list.append(new_item)
                if is_trackable(new_item):
                    self._tracking_add_child_tracked_item(count, item)
                count += 1
            super().extend(new_list)
        else:
            new_list = items

        extend_length = len(new_list)
        current_leng = len(self)

        locations = [str(i - 1) for i in range(current_leng - 1, current_leng - 1 + extend_length)]
        location = ','.join(locations)

        extra['data_post_change'] = repr(self)
        self.tracking_create_change(action='add', method=sys._getframe().f_code.co_name,
                                          location=location, value=items, **extra)

    def insert(self, index, item):
        """
        insert an item
        """
        extra = {'data_pre_change': repr(self)}

        if not self._tracking_locked:
            item = self._tracking_convert_value(item)
            super().insert(index, item)
            if is_trackable(item):
                self._tracking_add_child_tracked_item(index, item)

        extra['data_post_change'] = repr(self)
        self.tracking_create_change(action='add', method=sys._getframe().f_code.co_name,
                                          location=index, value=item, **extra)

    def remove(self, item):
        """
        remove an item
        """
        extra = {'data_pre_change': repr(self)}

        index = super().index(item)
        if not self._tracking_locked:
            super().remove(item)
            if is_trackable(item):
                self._tracking_remove_child_tracked_item(item)

        extra['data_post_change'] = repr(self)
        self.tracking_create_change(action='remove', method=sys._getframe().f_code.co_name,
                                          location=index, value=item, **extra)

    def pop(self, index=-1):
        """
        pop an item
        """
        extra = {'data_pre_change': repr(self)}
        actual_index = index
        if index == -1:
            actual_index = len(self) - 1
            extra['passed_index'] = str(-1)

        if not self._tracking_locked:
            item = super().pop(index)
            if is_trackable(item):
                # ChangeLogEntry(is_trackable(item), item._tracking_uuid,
                #                    action='remove', removed_from = self.__class__.__name__,
                #                    method='pop', related_uuid=self._tracking_uuid)
                self._tracking_remove_child_tracked_item(item)

        extra['data_post_change'] = repr(self)
        self.tracking_create_change(action='remove', method=sys._getframe().f_code.co_name,
                                          location=actual_index, value=item,
                                          **extra)

        return item

    def clear(self):
        """
        clear the list
        """
        extra = {'data_pre_change': repr(self)}
        if not self._tracking_locked:
            for item in self:
                if is_trackable(item):
                    # ChangeLogEntry(item.__class__.__name__, item._tracking_uuid,
                    #                action='removed', removed_from = self.__class__.__name__,
                    #                method='clear', related_uuid=self._tracking_uuid)
                    self._tracking_remove_child_tracked_item(item)

            super().clear()

        extra['data_post_change'] = repr([])
        self.tracking_create_change(action='remove', method=sys._getframe().f_code.co_name,
                                     **extra)

    def sort(self, key=None, reverse=False):
        """
        sort the list
        """
        extra = {'data_pre_change': repr(self)}
        if not self._tracking_locked:
            super().sort(key=key, reverse=reverse)
            for item in self._tracking_child_tracked_items:
                self._tracking_child_tracked_items[item]['index'] = self.index(item)

        extra['data_post_change'] = repr(self)
        self.tracking_create_change(action='update', method=sys._getframe().f_code.co_name,
                                    **extra)

    def reverse(self):
        """
        reverse the list
        """
        extra = {'data_pre_change': repr(self)}
        if not self._tracking_locked:
            super().reverse()
            for item in self._tracking_child_tracked_items:
                self._tracking_child_tracked_items[item]['index'] = self.index(item)

        extra['data_post_change'] = repr(self)
        self.tracking_create_change(action='update', method=sys._getframe().f_code.co_name,
                                    **extra)

    def copy(self, untracked=True):
        """
        copy the list
        """
        new_list = convert_to_untrackable(self) if untracked else super().copy()
        self.tracking_create_change(action='copy', method=sys._getframe().f_code.co_name)
        return new_list
