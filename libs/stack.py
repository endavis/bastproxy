# Project: bastproxy
# Filename: libs/stack.py
#
# File Description: a simple stack class
#
# By: Bast
"""Module for managing a simple stack data structure.

This module provides the `SimpleStack` class, which implements a basic stack
with additional features such as snapshots and item lookup by ID. It includes
methods for standard stack operations like push, pop, and peek, as well as
utility methods for managing snapshots and retrieving items by ID.

Key Components:
    - SimpleStack: A class that implements a simple stack data structure.
    - Methods for pushing, popping, peeking, and removing items from the stack.
    - Utility methods for taking snapshots and retrieving items by ID.

Features:
    - Basic stack operations: push, pop, peek, and size.
    - Snapshot functionality to capture the current state of the stack.
    - ID-based item lookup for stacks with dictionary items.

Usage:
    - Instantiate SimpleStack to create a stack object.
    - Use `push` to add items to the stack and `pop` to remove items.
    - Use `takesnapshot` to capture the current state of the stack.
    - Retrieve items by ID using `get_by_id` if the stack items are dictionaries.

Classes:
    - `SimpleStack`: Represents a simple stack data structure with additional features.

"""

# Standard Library
from typing import Any

# 3rd Party

# Project


class SimpleStack:
    """A simple stack data structure with additional features.

    This class implements a basic stack with methods for standard stack operations
    such as push, pop, and peek. It also includes utility methods for managing
    snapshots and retrieving items by ID when the stack items are dictionaries.

    """

    def __init__(self, length: int = 20, id_key: str | None = None) -> None:
        """Initialize the stack with a specified length and optional ID key.

        This method initializes the stack with a given length and an optional ID key
        for items that are dictionaries. The ID key is used for looking up items by
        their ID.

        Args:
            length: The maximum length of the stack.
            id_key: The key used to identify items in the stack if they are
                dictionaries.

        Returns:
            None

        Raises:
            None

        """
        self.len: int = length
        self.items: list = []
        self.snapshot: SimpleStack | None = None
        self.id_key: str | None = id_key
        self.id_lookup: dict[str, Any] = {}

    def isempty(self) -> bool:
        """Check if the stack is empty.

        This method checks whether the stack is empty by comparing the items list
        to an empty list.

        Args:
            None

        Returns:
            True if the stack is empty, False otherwise.

        Raises:
            None

        """
        return self.items == []

    def push(self, item: Any) -> None:
        """Push an item onto the stack.

        This method adds an item to the top of the stack. If the stack exceeds its
        maximum length, the oldest item is removed to maintain the stack size.

        Args:
            item: The item to push onto the stack.

        Returns:
            None

        Raises:
            None

        """
        self.items.append(item)
        while len(self.items) > self.len:
            self.items.pop(0)

    def pop(self) -> Any:
        """Pop an item from the stack.

        This method removes and returns the top item from the stack. If the stack
        is empty, it raises an IndexError.

        Args:
            None

        Returns:
            The item that was removed from the top of the stack.

        Raises:
            IndexError: If the stack is empty.

        """
        return self.items.pop()

    def remove(self, item: Any) -> None:
        """Remove an item from the stack.

        This method removes a specified item from the stack. If the item is not found,
        it raises a ValueError.

        Args:
            item: The item to remove from the stack.

        Returns:
            None

        Raises:
            ValueError: If the item is not found in the stack.

        """
        self.items.remove(item)

    def peek(self) -> Any | None:
        """Peek at the top item of the stack without removing it.

        This method returns the top item of the stack without removing it. If the
        stack is empty, it returns None.

        Args:
            None

        Returns:
            The top item of the stack if it exists, otherwise None.

        Raises:
            None

        """
        return self.items[-1] if len(self.items) > 0 else None

    def size(self) -> int:
        """Get the current size of the stack.

        This method returns the number of items currently in the stack.

        Args:
            None

        Returns:
            The number of items in the stack.

        Raises:
            None

        """
        return len(self.items)

    def takesnapshot(self) -> None:
        """Take a snapshot of the current stack state.

        This method creates a snapshot of the current stack state by copying the
        items and storing them in a new SimpleStack instance.

        Args:
            None

        Returns:
            None

        Raises:
            None

        """
        self.snapshot = SimpleStack(self.len, id_key=self.id_key)
        self.snapshot.items = self.items[:]

    def getstack(self) -> list:
        """Get a copy of the current stack items.

        This method returns a shallow copy of the current stack items list.

        Args:
            None

        Returns:
            A list containing the current stack items.

        Raises:
            None

        """
        return self.items[:]

    def getsnapshot(self) -> "SimpleStack | None":
        """Get the snapshot of the stack.

        This method returns the snapshot of the stack if it exists. The snapshot
        is a SimpleStack instance that contains a copy of the stack items at the
        time the snapshot was taken.

        Args:
            None

        Returns:
            The snapshot of the stack if it exists, otherwise None.

        Raises:
            None

        """
        return self.snapshot

    def get_by_id(self, item_id: str) -> Any | None:
        """Retrieve an item from the stack by its ID.

        This method searches for an item in the stack by its ID. The ID is determined
        by the `id_key` provided during the initialization of the stack. If the item
        is found, it is returned; otherwise, None is returned.

        Args:
            item_id: The ID of the item to retrieve from the stack.

        Returns:
            The item with the specified ID if found, otherwise None.

        Raises:
            None

        """
        if self.id_key:
            for item in self.items:
                if item[self.id_key] == item_id:
                    return item

        return None
