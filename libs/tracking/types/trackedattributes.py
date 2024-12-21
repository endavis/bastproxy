# -*- coding: utf-8 -*-
# Project: bastproxy
# Filename: libs/tracking/utils/attributes.py
#
# File Description: Holds a class that monitors attributes
#
# Docstrings last checked and updated: 12/19/2024
#
# By: Bast
"""Module for monitoring and managing attributes with tracking capabilities.

This module provides the `TrackedAttr` class, which allows for the tracking
of changes to attributes and the management of relationships between tracked
attributes and their children. It includes methods for locking and unlocking
attributes, notifying observers of changes, and maintaining a history of
original values, making it a valuable tool for monitoring state changes in
an application.

Key Components:
    - TrackedAttr: A class that extends TrackBase to monitor attribute changes.
    - Methods for adding, locking, unlocking, and notifying changes to attributes.
    - Utility methods for handling attribute changes, conversions, and tracking.

Features:
    - Automatic conversion of tracked attribute values.
    - Management of parent-child relationships for tracked attributes.
    - Notification system for observers when attribute changes occur.
    - Locking mechanism to prevent modifications to specific attributes.
    - Comprehensive logging of attribute changes and original values.

Usage:
    - Instantiate TrackedAttr to create an object that tracks attribute changes.
    - Use `tracking_add_attribute_to_monitor` to start monitoring specific attributes.
    - Lock and unlock attributes using `lock` and `unlock` methods.
    - Access original values and change logs through provided methods.

Classes:
    - `TrackedAttr`: Represents a class that can track attribute changes.

"""
# Standard Library
import contextlib
import sys
from typing import Any, TYPE_CHECKING

# 3rd Party

# Project
from ..types._trackbase import TrackBase, track_changes

if TYPE_CHECKING:
    from libs.tracking.utils.changelog import ChangeLogEntry


class TrackedAttr(TrackBase):
    """Class for tracking and managing changes to attributes.

    This class extends the TrackBase class to provide functionality for monitoring
    changes to attributes, managing parent-child relationships, and handling
    attribute locking and unlocking. It includes methods for adding attributes to
    the monitoring list, notifying observers of changes, and maintaining original
    values of attributes.

    """

    def __init__(
        self,
        tracking_auto_convert: bool = True,
        tracking_parent: "TrackBase | None" = None,
        tracking_location: str | None = "",
    ) -> None:
        """Initialize a TrackedAttr instance.

        This constructor initializes the TrackedAttr instance with the provided
        parameters for automatic conversion, parent tracking, and location tracking.
        It also sets up the base tracking attributes, including the list of attributes
        to monitor, locked attributes, and original values.

        Args:
            tracking_auto_convert: Whether to automatically convert tracked attribute
                values.
            tracking_parent: The parent TrackBase instance for hierarchical tracking.
            tracking_location: The location identifier for the tracked attribute.
            tracking_delimiter: The delimiter used to separate tracking locations.

        Returns:
            None

        """
        TrackBase.__init__(
            self,
            tracking_auto_convert=tracking_auto_convert,
            tracking_parent=tracking_parent,
            tracking_location=tracking_location,
            tracking_delimiter=".",
        )
        self._tracking_attributes_to_monitor = []
        self._tracking_locked_attributes = []
        self._tracking_original_values = {}

    def _tracking_is_tracking_attribute(self, attribute_name: str) -> bool:
        """Check if the specified attribute is being tracked.

        This method verifies whether the given attribute name is present in the list
        of attributes being monitored. It returns False if the monitoring list does
        not exist.

        Args:
            attribute_name: The name of the attribute to check.

        Returns:
            True if the attribute is being tracked; otherwise, False.

        """
        if not hasattr(self, "_tracking_attributes_to_monitor"):
            return False
        return attribute_name in self._tracking_attributes_to_monitor

    def _tracking_is_locked_attribute(self, attribute_name: str) -> bool:
        """Check if the specified attribute is locked.

        This method verifies whether the given attribute name is present in the list
        of locked attributes. It returns False if the locked attributes list does
        not exist.

        Args:
            attribute_name: The name of the attribute to check.

        Returns:
            True if the attribute is locked; otherwise, False.

        """
        if not hasattr(self, "_tracking_locked_attributes"):
            return False
        return attribute_name in self._tracking_locked_attributes

    def _tracking_notify_observers(self, change_log_entry: "ChangeLogEntry") -> None:
        """Notify observers of attribute changes.

        This method notifies observers of changes to tracked attributes by creating
        a new change log entry if necessary and updating the tracking context. It
        ensures that any changes to the attributes are communicated to the observers,
        maintaining the integrity of the tracking system.

        Args:
            change_log_entry: The entry in the change log that describes the
                attribute change.

        Returns:
            None

        """
        if change_log_entry.tracked_item_uuid != self._tracking_uuid:
            for item in self._tracking_attributes_to_monitor:
                value = getattr(self, item)
                if (
                    self._tracking_is_trackable(value)
                    and value._tracking_uuid == change_log_entry.tracked_item_uuid
                ):
                    new_change = change_log_entry.copy(
                        change_log_entry.extra["type"], self._tracking_uuid
                    )
                    new_change.add_to_tree(self._tracking_format_tree_location(item))
                    if "location" in new_change.extra:
                        new_change.extra["location"] = (
                            f"{item}{value._tracking_delimiter}{new_change.extra['location']}"
                        )
                    else:
                        new_change.extra["location"] = f"{item}"

                    change_log_entry = new_change

                    break

        if change_log_entry not in self._tracking_changes:
            self._tracking_changes.append(change_log_entry)
        super()._tracking_notify_observers(change_log_entry)

    def tracking_add_attribute_to_monitor(self, attribute_name: str) -> None:
        """Add an attribute to the monitoring list.

        This method adds the specified attribute to the list of attributes being
        monitored. If the attribute exists and is not already being monitored, it
        is appended to the monitoring list, and its original value is stored. The
        attribute value is then converted if necessary, and a change log entry is
        created to record the start of monitoring.

        Args:
            attribute_name: The name of the attribute to be monitored.

        Returns:
            None

        """
        if (
            hasattr(self, attribute_name)
            and attribute_name not in self._tracking_attributes_to_monitor
        ):
            self._tracking_attributes_to_monitor.append(attribute_name)
            original_value = value = getattr(self, attribute_name)
            value = self._tracking_convert_value(value, attribute_name)
            super().__setattr__(attribute_name, value)
            self.tracking_create_change(
                action="start monitoring",
                location=f"{attribute_name}",
                value=original_value,
            )

    def _tracking_attribute_change(
        self, method: str, attribute_name: str, original_value: Any, new_value: Any
    ) -> None:
        """Handle changes to tracked attributes and log the changes.

        This method is responsible for tracking changes to attributes by comparing
        the original value with the new value. If the values differ, it creates a
        change log entry that captures the details of the update, including the
        method that triggered the change and the state of the attribute before and
        after the change.

        Args:
            method: The name of the method that triggered the attribute change.
            attribute_name: The name of the attribute that has changed.
            original_value: The original value of the attribute before the change.
            new_value: The new value of the attribute after the change.

        Returns:
            None

        """
        if original_value == "#!NotSet":
            with contextlib.suppress(Exception):
                self._tracking_original_values[attribute_name] = new_value
        if original_value not in ["#!NotSet", new_value]:
            extra = {
                "data_pre_change": original_value,
                "data_post_change": getattr(self, attribute_name),
            }
            self.tracking_create_change(
                action="update",
                method=method,
                location=f"{attribute_name}",
                value=new_value,
                attribute_locked=self._tracking_is_locked_attribute(attribute_name),
                **extra,
            )

    def _tracking_convert_all_values(self) -> None:
        """Convert all tracked attribute values to their appropriate types.

        This method is intended to process and convert all values of the tracked
        attributes within the instance. It does not apply to this object because
        specific attributes are converted as needed when they are tracked.

        Args:
            None

        Returns:
            None

        """
        pass

    def _tracking_get_original_value(self, attribute_name: str) -> Any:
        """Retrieve the original value of a specified tracked attribute.

        This method looks up the original value of the given attribute name from
        the dictionary that stores original values. If the attribute name is not
        found, it returns None.

        Args:
            attribute_name: The name of the attribute whose original value
                is to be retrieved.

        Returns:
            The original value of the specified attribute, or None if the
                attribute does not exist.

        """
        return self._tracking_original_values.get(attribute_name, None)

    @track_changes
    def _tracking_lock_attribute(self, attribute_name) -> None:
        """Lock a specified attribute to prevent modifications.

        This method adds the given attribute name to the list of locked attributes,
        ensuring that its value cannot be changed until it is unlocked. If the
        attribute is trackable, it also invokes the lock method on the attribute,
        maintaining the integrity of the tracking system.

        Args:
            attribute_name: The name of the attribute to be locked.

        Returns:
            None

        """
        if not hasattr(self, attribute_name):
            return

        self._tracking_locked_attributes.append(attribute_name)
        value = getattr(self, attribute_name)
        if self._tracking_is_trackable(value):
            value.lock()

        self._tracking_context["action"] = "lock"
        self._tracking_context["attribute_name"] = attribute_name
        self._tracking_context["attribute_locked"] = self._tracking_is_locked_attribute(
            attribute_name
        )

    def _tracking_unlock_attribute(self, attribute_name: str = "") -> None:
        """Unlock a specified attribute to allow modifications.

        This method removes the given attribute name from the list of locked
        attributes, enabling changes to be made to its value. If the attribute is
        trackable, it also invokes the unlock method on the attribute, ensuring
        that the attribute can be modified.

        Args:
            attribute_name: The name of the attribute to be unlocked.

        Returns:
            None

        """
        if not hasattr(self, attribute_name):
            return

        if attribute_name in self._tracking_locked_attributes:
            value = getattr(self, attribute_name)
            if self._tracking_is_trackable(value):
                value.unlock()

            self._tracking_locked_attributes.remove(attribute_name)
            self.tracking_create_change(
                action="unlock",
                attribute_name=attribute_name,
                attribute_locked=self._tracking_is_locked_attribute(attribute_name),
            )

    @track_changes
    def lock(self, attribute_name: str = "") -> None:
        """Lock specified attributes to prevent modifications.

        This method locks the given attribute or all monitored attributes,
        preventing changes to their values. It updates the tracking context
        to reflect the locking action, ensuring that data integrity is maintained.

        Args:
            attribute_name: The name of the attribute to be locked.
                If not provided, all monitored attributes will be locked.

        Returns:
            None

        """
        if attribute_name:
            self._tracking_lock_attribute(attribute_name)
        else:
            for attribute in self._tracking_attributes_to_monitor:
                self._tracking_lock_attribute(attribute)
            self._tracking_locked = True

            # self.tracking_create_change(action='lock')
            self._tracking_context["action"] = "lock"

    def unlock(self, attribute_name: str = "") -> None:
        """Unlock specified attributes to allow modifications.

        This method unlocks the given attribute or all monitored attributes,
        enabling changes to their values. It updates the tracking context
        to reflect the unlocking action, ensuring that data integrity is maintained.

        Args:
            attribute_name: The name of the attribute to be unlocked.
                If not provided, all monitored attributes will be unlocked.

        Returns:
            None

        """
        if attribute_name:
            self._tracking_unlock_attribute(attribute_name)
        else:
            self._tracking_locked = False
            for attribute in self._tracking_attributes_to_monitor:
                self._tracking_unlock_attribute(attribute)

            self.tracking_create_change(action="unlock")

    def __setattr__(self, attribute_name: str, value: Any) -> None:
        """Set the value of the specified attribute.

        This method sets the value of the given attribute name. It first checks
        if the attribute is locked, and if so, raises a RuntimeError. It then
        retrieves the original value of the attribute and, if the attribute is
        being tracked, converts the new value if necessary. Finally, it updates
        the attribute value and logs the change if the attribute is being tracked.

        Args:
            attribute_name: The name of the attribute to set.
            value: The new value to assign to the attribute.

        Returns:
            None

        Raises:
            RuntimeError: If the attribute is locked and cannot be modified.

        """
        if self._tracking_is_locked_attribute(attribute_name):
            raise RuntimeError(
                f"{self.__class__.__name__}.{attribute_name} is locked and cannot be "
                "modified."
            )

        try:
            original_value = getattr(self, attribute_name)
        except AttributeError:
            original_value = "#!NotSet"

        if (
            not self._tracking_is_tracking_attribute(attribute_name)
            or not (self._tracking_is_locked_attribute(attribute_name))
            and (hasattr(self, "_tracking_locked") and not self._tracking_locked)
        ):
            if self._tracking_is_tracking_attribute(attribute_name):
                value = self._tracking_convert_value(value, attribute_name)
            super().__setattr__(attribute_name, value)

        if self._tracking_is_tracking_attribute(attribute_name):
            self._tracking_attribute_change(
                sys._getframe().f_code.co_name, attribute_name, original_value, value
            )

    def _tracking_known_uuids_tree(
        self, level: int = 0, attribute_name: str = "", emptybar: dict | None = None
    ) -> list:
        """Generate a tree of known UUIDs for tracked attributes.

        This method generates a hierarchical representation of known UUIDs for
        tracked attributes, allowing for easy visualization of the relationships
        between them. It can process a specific attribute or all monitored attributes
        to construct the tree structure.

        Args:
            level: The current level of the tree traversal.
            attribute_name: The name of the attribute to start the traversal from.
            emptybar: A dictionary to track the state of the tree traversal.

        Returns:
            A list of strings representing the tree structure of known UUIDs.

        """
        if emptybar is None:
            emptybar = {}
        known_uuids = []
        if level == 0:
            emptybar[level] = True
            known_uuids.append(
                f"{self._tracking_is_trackable(self)}:{self._tracking_uuid}"
            )
            level += 1
        if attribute_name:
            emptybar[level] = True
            pre_string = "".join(
                "    " if emptybar[i] else " |  " for i in range(level)
            )
            value = getattr(self, attribute_name)
            known_uuids.append(
                f"{pre_string} |-> Location: {attribute_name} Item: "
                f"{self._tracking_is_trackable(value)}:{value._tracking_uuid}"
            )

            known_uuids.extend(
                value._tracking_known_uuids_tree(level + 1, emptybar=emptybar)
            )

        else:
            emptybar[level] = False
            left = self._tracking_attributes_to_monitor[:]
            pre_string = "".join(
                "    " if emptybar[i] else " |  " for i in range(level)
            )
            for attribute_name in self._tracking_attributes_to_monitor:
                left.remove(attribute_name)
                if not left:
                    emptybar[level] = True
                value = getattr(self, attribute_name)
                if self._tracking_is_trackable(value):
                    known_uuids.append(
                        f"{pre_string} |-> Location: {attribute_name} Item: "
                        f"{self._tracking_is_trackable(value)}:{value._tracking_uuid}"
                    )

                    known_uuids.extend(
                        value._tracking_known_uuids_tree(level + 1, emptybar=emptybar)
                    )
        return known_uuids

    def _tracking_format_tree_location(
        self, location: str | None = None
    ) -> dict[str, str]:
        """Format the tree location for a tracked attribute.

        This method constructs a dictionary that represents the type, UUID, and
        location of the tracked attribute within a hierarchical structure. It
        provides a way to format the information for better organization and
        visualization of tracked attributes.

        Args:
            location: The location identifier for the tracked attribute.

        Returns:
            A dictionary containing the type, UUID, and location of the tracked
            attribute.

        """
        if location is not None:
            return {
                "type": self._tracking_is_trackable(self),
                "uuid": self._tracking_uuid,
                "location": f".{location}",
            }
        return {"type": self._tracking_is_trackable(self), "uuid": self._tracking_uuid}
