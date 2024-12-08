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
from ._trackbase import TrackBase

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
            item = self._tracking_convert_value(item, index)
            super().__setitem__(index, item)
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
            index = len(self)
            item = self._tracking_convert_value(item, index)
            super().append(item)

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

        extra['data_post_change'] = repr(self)
        self.tracking_create_change(action='add', method=sys._getframe().f_code.co_name,
                                          location=location, value=items, **extra)

    def insert(self, index, item):
        """
        insert an item
        """
        extra = {'data_pre_change': repr(self)}

        if not self._tracking_locked:
            item = self._tracking_convert_value(item, index)
            super().insert(index, item)

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
        new_list = self._tracking_convert_to_untrackable(self) if untracked else super().copy()
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

