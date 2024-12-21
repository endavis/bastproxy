# -*- coding: utf-8 -*-
# Project: bastproxy
# Filename: libs/tracking/types/trackedlist.py
#
# File Description: Holds a list implementation with change tracking.
#
# Docstrings last checked and updated: 12/19/2024
#
# By: Bast
"""Module for monitoring and managing a list with tracking capabilities.

This module provides the `TrackedList` class, which allows for the tracking
of changes to lists and the management of relationships between their children.
It includes methods for locking and unlocking the list, notifying observers of
changes, and maintaining a history of original values, making it a valuable tool
for monitoring state changes in an application.

Key Components:
    - TrackedList: A class that extends TrackBase and list to monitor list
        changes.
    - Methods for adding, locking, unlocking, and notifying changes to the list.
    - Utility methods for handling list item changes, conversions, and tracking.

Features:
    - Automatic conversion of tracked values.
    - Management of parent-child relationships for tracked children.
    - Notification system for observers when list data changes occur.
    - Locking mechanism to prevent modifications to the list
    - Comprehensive logging of data changes and original values.

Usage:
    - Instantiate TrackedList to create an object that tracks list changes.
    - Lock and unlock the list using `lock` and `unlock` methods.
    - Access original values and change logs through provided methods.

Classes:
    - `TrackedList`: Represents a class that can track list changes.

"""

# Standard Library
from typing import TYPE_CHECKING, Any, Callable

# 3rd Party

# Project
from ._trackbase import TrackBase, track_changes, check_lock

if TYPE_CHECKING:
    from ..utils.changelog import ChangeLogEntry


class TrackedList(TrackBase, list):
    """A list class that tracks changes to its items.

    This class extends both TrackBase and Python's built-in list to provide
    comprehensive change tracking capabilities. It is designed for applications
    that require monitoring and logging modifications to dictionary data structures.
    The class includes methods for locking and unlocking the list, notifying
    observers of changes, and maintaining a history of original values.

    """

    def __init__(
        self,
        data: list | None = None,
        tracking_auto_converted_in: str | None = None,
        tracking_auto_convert: bool = False,
        tracking_parent: "TrackBase | None" = None,
        tracking_location: str | None = "",
    ) -> None:
        """Initialize the tracked list.

        This constructor initializes the tracked list with optional initial data,
        tracking settings, and parent-child relationship management.

        Args:
            data: The initial data for the list.
            tracking_auto_converted_in: The attribute to automatically convert in.
            tracking_auto_convert: Whether to automatically convert values.
            tracking_parent: The parent tracking object.
            tracking_location: The location of the tracking object.

        """
        if data is None:
            data = []
        list.__init__(self, data)
        TrackBase.__init__(
            self,
            tracking_auto_converted_in=tracking_auto_converted_in,
            tracking_auto_convert=tracking_auto_convert,
            tracking_parent=tracking_parent,
            tracking_location=tracking_location,
            tracking_delimiter="|",
        )

    def _tracking_convert_all_values(self) -> None:
        """Convert all values in the dictionary to tracked objects.

        Iterates through all key-value pairs in the dictionary and converts each value
        to a tracked object if it is not already one. This ensures that all values in
        the dictionary are trackable and can be monitored for changes.

        """
        for index, value in enumerate(self):
            self[index] = self._tracking_convert_value(value, index)

    def _tracking_notify_observers(self, change_log_entry: "ChangeLogEntry") -> None:
        """Notify observers of a change in the tracked dictionary.

        This method is called to notify all registered observers about a change in the
        tracked dictionary. It processes the change log entry, updates the tracking
        context, and ensures that the change is propagated to all observers.

        Args:
            change_log_entry: The entry in the change log that describes the
                attribute change.

        """
        if (
            change_log_entry.tracked_item_uuid != self._tracking_uuid
            and change_log_entry.tracked_item_uuid in self._tracking_child_tracked_items
        ):
            new_change = change_log_entry.copy(
                change_log_entry.extra["type"], self._tracking_uuid
            )
            new_change.add_to_tree(
                self._tracking_format_tree_location(
                    self._tracking_child_tracked_items[
                        change_log_entry.tracked_item_uuid
                    ]["location"]
                )
            )
            if "location" in new_change.extra:
                delimiter = self._tracking_child_tracked_items[
                    change_log_entry.tracked_item_uuid
                ]["item"]._tracking_delimiter
                new_change.extra["location"] = (
                    f'{self._tracking_child_tracked_items[change_log_entry.tracked_item_uuid]["location"]}{delimiter}{new_change.extra['location']}'
                )
            else:
                new_change.extra["location"] = (
                    f'{self._tracking_child_tracked_items[change_log_entry.tracked_item_uuid]["location"]}'
                )

            change_log_entry = new_change

        if change_log_entry not in self._tracking_changes:
            self._tracking_changes.append(change_log_entry)
        super()._tracking_notify_observers(change_log_entry)

    @check_lock
    @track_changes
    def __setitem__(self, index: int, item: Any) -> None:
        """Set an item in the tracked list.

        This method sets an item at the specified index in the tracked list,
        converting the item to a tracked value if necessary. It also updates
        the tracking context with the action details.

        Args:
            index: The index at which to set the item.
            item: The item to set in the list.

        Raises:
            TypeError: If the index is not an integer.

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
            self._tracking_context.setdefault("removed_items", []).append(old_item)
        self._tracking_context["action"] = "update"
        self._tracking_context["value"] = item
        self._tracking_context["location"] = index

    @check_lock
    @track_changes
    def __delitem__(self, index: int) -> None:
        """Delete an item from the tracked list.

        This method deletes an item at the specified index from the tracked list,
        updating the tracking context with the action details.

        Args:
            index: The index of the item to delete.

        Raises:
            TypeError: If the index is not an integer.

        Example:
            >>> tracked_list = TrackedList([1, 2, 3])
            >>> del tracked_list[1]  # Deletion is tracked
            >>> del tracked_list[5]  # Raises IndexError

        """
        if not isinstance(index, int):
            raise TypeError(f"Tracked list index must be an int, not {type(index)}")

        old_item = self[index]
        if not self._tracking_locked:
            super().__delitem__(index)

        self._tracking_context.setdefault("removed_items", []).append(old_item)
        self._tracking_context["action"] = "update"
        self._tracking_context["value"] = old_item
        self._tracking_context["location"] = index

    @check_lock
    @track_changes
    def append(self, item: Any) -> None:
        """Append an item to the tracked list.

        This method appends an item to the end of the tracked list, converting
        the item to a tracked value if necessary. It also updates the tracking
        context with the action details.

        Args:
            item: The item to append to the list.

        Example:
            >>> tracked_list = TrackedList([1, 2, 3])
            >>> tracked_list.append(4)  # Append is tracked
            >>> tracked_list.append('a')  # Append is tracked

        """
        index = "none"

        if not self._tracking_locked:
            index = len(self)
            item = self._tracking_convert_value(item, index)
            super().append(item)

        self._tracking_context["action"] = "add"
        self._tracking_context["value"] = item
        self._tracking_context["location"] = index

    @check_lock
    @track_changes
    def extend(self, items: list) -> None:
        """Extend the tracked list with items from another list.

        This method extends the tracked list by appending items from another list,
        converting each item to a tracked value if necessary. It also updates the
        tracking context with the action details.

        Args:
            items: The list of items to extend the tracked list with.

        Example:
            >>> tracked_list = TrackedList([1, 2, 3])
            >>> tracked_list.extend([4, 5])  # Extend is tracked
            >>> tracked_list.extend(['a', 'b'])  # Extend is tracked

        """
        if not self._tracking_locked:
            new_data = []
            count = len(self)
            for item in items:
                new_item = self._tracking_convert_value(item, count)
                new_data.append(new_item)
                count += 1
            super().extend(new_data)
        else:
            new_data = items

        extend_length = len(new_data)
        current_leng = len(self)

        locations = [
            str(i - 1)
            for i in range(current_leng - 1, current_leng - 1 + extend_length)
        ]
        location = ",".join(locations)

        self._tracking_context["action"] = "add"
        self._tracking_context["value"] = items
        self._tracking_context["location"] = location

    @check_lock
    @track_changes
    def insert(self, index: int, item: Any) -> None:
        """Insert an item into the tracked list.

        This method inserts an item at the specified index in the tracked list,
        converting the item to a tracked value if necessary. It also updates
        the tracking context with the action details.

        Args:
            index: The index at which to insert the item.
            item: The item to insert into the list.

        Raises:
            TypeError: If the index is not an integer.

        Example:
            >>> tracked_list = TrackedList([1, 2, 3])
            >>> tracked_list.insert(1, 4)  # Insert is tracked
            >>> tracked_list.insert(5, 'a')  # Insert is tracked

        """
        if not self._tracking_locked:
            item = self._tracking_convert_value(item, index)
            super().insert(index, item)

        self._tracking_context["action"] = "add"
        self._tracking_context["value"] = item
        self._tracking_context["location"] = index

    @check_lock
    @track_changes
    def remove(self, item: Any) -> None:
        """Remove an item from the tracked list.

        This method removes the first occurrence of the specified item from the
        tracked list, updating the tracking context with the action details.

        Args:
            item: The item to remove from the list.

        Raises:
            ValueError: If the item is not found in the list.

        Example:
            >>> tracked_list = TrackedList([1, 2, 3])
            >>> tracked_list.remove(2)  # Remove is tracked
            >>> tracked_list.remove(5)  # Raises ValueError

        """
        try:
            index = super().index(item)
        except ValueError:
            index = None

        if not self._tracking_locked:
            super().remove(item)

        if index:
            self._tracking_context.setdefault("removed_items", []).append(item)

        self._tracking_context["action"] = "remove"
        self._tracking_context["value"] = item
        self._tracking_context["location"] = index

    @check_lock
    @track_changes
    def pop(self, index: int = -1) -> Any:
        """Remove and return an item from the tracked list.

        This method removes and returns an item at the specified index from the
        tracked list, updating the tracking context with the action details.

        Args:
            index: The index of the item to remove and return. Defaults to -1.

        Returns:
            The item removed from the list.

        Raises:
            IndexError: If the index is out of range.
            TypeError: If the index is not an integer.

        Example:
            >>> tracked_list = TrackedList([1, 2, 3])
            >>> tracked_list.pop()  # Pop is tracked
            3
            >>> tracked_list.pop(0)  # Pop is tracked
            1
            >>> tracked_list.pop(5)  # Raises IndexError

        """
        passed_index = index
        actual_index = index

        if passed_index == -1:
            actual_index = len(self) - 1

        item = "###^$^@$^$default###^$^@$^"
        if not self._tracking_locked:
            item = super().pop(index)

        if item != "###^$^@$^$default###^$^@$^":
            self._tracking_context.setdefault("removed_items", []).append(item)
        self._tracking_context["action"] = "remove"
        self._tracking_context["value"] = (
            None if item == "###^$^@$^$default###^$^@$^" else item
        )
        self._tracking_context["location"] = actual_index
        self._tracking_context["passed_index"] = passed_index

        return item

    @check_lock
    @track_changes
    def clear(self) -> None:
        """Clear all items from the tracked list.

        This method clears all items from the tracked list, updating the tracking
        context with the action details.

        Example:
            >>> tracked_list = TrackedList([1, 2, 3])
            >>> tracked_list.clear()  # Clear is tracked

        """
        if not self._tracking_locked:
            for item in self:
                self._tracking_context.setdefault("removed_items", []).append(item)

            super().clear()

        self._tracking_context["action"] = "remove"

    @check_lock
    @track_changes
    def sort(self, key: Callable | None = None, reverse: bool = False) -> None:
        """Sort the tracked list.

        This method sorts the tracked list in place, updating the tracking context
        with the action details. It also updates the indices of tracked child items.

        Args:
            key: A function that serves as a key for the sort comparison.
            reverse: Whether to sort the list in reverse order.

        Example:
            >>> tracked_list = TrackedList([3, 1, 2])
            >>> tracked_list.sort()  # Sort is tracked
            >>> tracked_list.sort(reverse=True)  # Sort is tracked

        """
        if not self._tracking_locked:
            super().sort(key=key, reverse=reverse)
            for item in self._tracking_child_tracked_items:
                self._tracking_child_tracked_items[item]["index"] = self.index(item)

        self._tracking_context["action"] = "update"

    @check_lock
    @track_changes
    def reverse(self) -> None:
        """Reverse the tracked list.

        This method reverses the order of items in the tracked list, updating the
        tracking context with the action details. It also updates the indices of
        tracked child items.

        Example:
            >>> tracked_list = TrackedList([1, 2, 3])
            >>> tracked_list.reverse()  # Reverse is tracked

        """
        if not self._tracking_locked:
            super().reverse()
            for item in self._tracking_child_tracked_items:
                self._tracking_child_tracked_items[item]["index"] = self.index(item)

        self._tracking_context["action"] = "update"

    @check_lock
    @track_changes
    def copy(self, untracked: bool = True) -> list[Any] | "TrackedList":
        """Copy the tracked list.

        This method creates a copy of the tracked list. If `untracked` is True,
        the copy will be a regular list without tracking capabilities. Otherwise,
        the copy will retain tracking capabilities.

        Args:
            untracked: Whether to create an untracked copy of the list.

        Returns:
            A copy of the tracked list.

        Example:
            >>> tracked_list = TrackedList([1, 2, 3])
            >>> new_list = tracked_list.copy()  # Copy is tracked
            >>> new_untracked_list = tracked_list.copy(untracked=True)  # Untracked copy

        """
        new_data = (
            self._tracking_convert_to_untrackable(self) if untracked else super().copy()
        )
        self._tracking_context["action"] = "copy"
        return new_data

    def _tracking_known_uuids_tree(
        self, level: int = 0, emptybar: dict[int, bool] | None = None
    ) -> list[str]:
        """Generate a list of known UUIDs in a tree structure.

        This method generates a list of known UUIDs for tracked items in the
        list, formatted as a tree structure. It helps visualize the
        hierarchy and relationships between tracked items.

        Args:
            level: The current depth level in the tree.
            emptybar: A dictionary tracking whether to show empty bars at each
                level.

        Returns:
            A list of strings representing the formatted UUID tree structure.

        """
        if emptybar is None:
            emptybar = {}
        known_uuids: list[str] = []
        if level == 0:
            emptybar[level] = True
            known_uuids.append(
                f"{self._tracking_is_trackable(self)}:{self._tracking_uuid}"
            )
            level += 1
        emptybar[level] = False
        pre_string = "".join("    " if emptybar[i] else " |  " for i in range(level))
        self._tracking_known_uuids_tree_helper(known_uuids, emptybar, level, pre_string)
        return known_uuids

    def _tracking_known_uuids_tree_helper(
        self,
        known_uuids: list[str],
        emptybar: dict[int, bool],
        level: int,
        pre_string: str,
    ) -> None:
        """Help method to generate a list of known UUIDs in a tree structure.

        This helper method assists in generating a list of known UUIDs for tracked
        items in the list, formatted as a tree structure. It helps visualize
        the hierarchy and relationships between tracked items.

        Args:
            known_uuids: The list to append the formatted UUID strings to.
            emptybar: A dictionary tracking whether to show empty bars at each
                level.
            level: The current depth level in the tree.
            pre_string: The prefix string for formatting the tree structure.

        """
        left = list(range(len(self)))
        for item in self:
            left.remove(self.index(item))
            if not left:
                emptybar[level] = True
            if self._tracking_is_trackable(item):
                known_uuids.append(
                    f"{pre_string} |-> Location: [{self.index(item)}] "
                    f"Item: {self._tracking_is_trackable(item)}:{item._tracking_uuid}"
                )
                known_uuids.extend(
                    item._tracking_known_uuids_tree(level + 1, emptybar=emptybar)
                )

    def _tracking_format_tree_location(self, location: str | int | None = None) -> dict:
        """Format the tree location for tracking purposes.

        This method formats the location of a tracked item in the list as a
        dictionary containing the type, UUID, and location of the item. It helps
        in visualizing and managing the hierarchy and relationships between tracked
        items.

        Args:
            location: The location of the tracked item in the list.

        Returns:
            A dictionary containing the type, UUID, and location of the tracked item.

        """
        if location is not None:
            return {
                "type": self._tracking_is_trackable(self),
                "uuid": self._tracking_uuid,
                "location": f"[{repr(location)}]",
            }
        return {"type": self._tracking_is_trackable(self), "uuid": self._tracking_uuid}
