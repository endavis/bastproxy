"""Module for monitoring and managing attribute changes with locking.

This module provides the `AttributeMonitor` class, which enables tracking
of attribute modifications, locking attributes to prevent changes, and
maintaining original values for monitored attributes.

Key Components:
    - AttributeMonitor: Base class for attribute change tracking.

Features:
    - Monitor specific attributes for changes.
    - Lock attributes to prevent modifications.
    - Store and retrieve original values of monitored attributes.
    - Context manager for temporary attribute locking.

Usage:
    - Inherit from AttributeMonitor to add monitoring to your class.
    - Use _attributes_to_monitor to specify which attributes to track.
    - Lock attributes using _locked_attributes list.

Classes:
    - `AttributeMonitor`: Monitors and manages attribute changes.

"""

import contextlib


class AttributeMonitor:
    """Base class for monitoring and managing attribute changes.

    This class provides infrastructure for tracking attribute modifications,
    locking specific attributes, and maintaining original values.

    """

    def __init__(self):
        """Initialize the attribute monitor with empty tracking lists."""
        self._attributes_to_monitor = []
        self._locked_attributes = []
        self._am_original_values = {}

    def __setattr__(self, name, value):
        """Intercept attribute setting for monitoring and locking.

        Args:
            name: The name of the attribute being set.
            value: The value being assigned to the attribute.

        """
        try:
            original_value = getattr(self, name)
        except AttributeError:
            original_value = "#!NotSet"
        if hasattr(self, "_locked_attributes") and name in self._locked_attributes:
            self._am_locked_attribute_update(name, value)
            return
        super().__setattr__(name, value)

        if hasattr(self, "_attributes_to_monitor") and name in self._attributes_to_monitor:
            self._attribute_set(name, original_value, value)

    def _attribute_set(self, name, original_value, new_value):
        change_func = getattr(self, f"_am_onchange_{name}", None)
        if original_value == "#!NotSet":
            with contextlib.suppress(Exception):
                self._am_original_values[name] = new_value
        if original_value not in ["#!NotSet", new_value]:
            self._am_onchange__all(name, original_value, new_value)
            if change_func:
                change_func(original_value, new_value)

    def _am_get_original_value(self, name):
        return self._am_original_values.get(name, None)

    def _am_onchange__all(self, name, original_value, new_value):
        pass

    def _am_lock_attribute(self, name):
        self._locked_attributes.append(name)

    def _am_unlock_attribute(self, name):
        self._locked_attributes.remove(name)

    def _am_locked_attribute_update(self, name, value):
        """Called when a locked attribute is attempted to be updated."""
