# Project: bastproxy
# Filename: libs/queue.py
#
# File Description: a simple queue class
#
# By: Bast
"""Module for managing a simple queue with optional ID-based lookups.

This module provides the `SimpleQueue` class, which implements a basic queue
with a fixed length. It supports standard queue operations such as enqueue,
dequeue, and size retrieval. Additionally, it offers snapshot functionality
and ID-based item lookups if an ID key is provided during initialization.

Key Components:
    - SimpleQueue: A class that implements a simple queue with optional ID-based
        lookups.
    - Methods for enqueuing, dequeuing, and retrieving the size of the queue.
    - Snapshot functionality to capture the current state of the queue.
    - ID-based item lookup if an ID key is provided.

Features:
    - Fixed-length queue with automatic removal of oldest items when the queue is
        full.
    - Snapshot functionality to capture and retrieve the state of the queue at a
        point in time.
    - ID-based item lookup for quick access to specific items if an ID key is
        provided.
    - Methods to get the last X items and to check if the queue is empty.

Usage:
    - Instantiate SimpleQueue with an optional length and ID key.
    - Use `enqueue` to add items to the queue and `dequeue` to remove items.
    - Retrieve the size of the queue with `size` and check if it is empty with
        `isempty`.
    - Capture the current state of the queue with `takesnapshot` and retrieve it
        with `getsnapshot`.
    - Use `get` to get a copy of the current items and `get_last_x` to get the last
        X items.
    - Use `get_by_id` to retrieve an item by its ID if an ID key is provided.

Classes:
    - `SimpleQueue`: Represents a simple queue with optional ID-based lookups.

"""
# Standard Library
from typing import Any, Iterator

# 3rd Party

# Project


class SimpleQueue(object):
    """A simple queue with optional ID-based lookups.

    This class implements a basic queue with a fixed length. It supports standard
    queue operations such as enqueue, dequeue, and size retrieval. Additionally,
    it offers snapshot functionality and ID-based item lookups if an ID key is
    provided during initialization.

    """

    def __init__(self, length: int = 10, id_key: str | None = None) -> None:
        """Initialize the SimpleQueue.

        This method initializes the SimpleQueue with a specified length and an
        optional ID key for item lookups.

        Args:
            length: The maximum length of the queue.
            id_key: The key used for ID-based lookups, if provided.

        Returns:
            None

        Raises:
            None

        """
        self.len: int = length
        self.items: list = []
        self.snapshot: SimpleQueue | None = None
        self.id_key: str | None = id_key
        self.id_lookup: dict[str, Any] = {}
        self.last_automatically_removed_item: Any = None

    def isempty(self) -> bool:
        """Check if the queue is empty.

        This method checks whether the queue is empty by comparing the items list
        to an empty list.

        Args:
            None

        Returns:
            bool: True if the queue is empty, False otherwise.

        Raises:
            None

        """
        return self.items == []

    def enqueue(self, item: Any) -> None:
        """Enqueue an item to the queue.

        This method adds an item to the end of the queue. If the queue exceeds its
        maximum length, the oldest item is automatically removed.

        Args:
            item: The item to be added to the queue.

        Returns:
            None

        Raises:
            None

        """
        self.items.append(item)
        while len(self.items) > self.len:
            self.last_automatically_removed_item = self.items.pop(0)

    def dequeue(self) -> Any:
        """Dequeue an item from the queue.

        This method removes and returns the oldest item from the queue. If the queue
        is empty, it raises an IndexError.

        Args:
            None

        Returns:
            The oldest item in the queue.

        Raises:
            IndexError: If the queue is empty.

        """
        return self.items.pop(0)

    def size(self) -> int:
        """Retrieve the current size of the queue.

        This method returns the number of items currently in the queue.

        Args:
            None

        Returns:
            The number of items in the queue.

        Raises:
            None

        """
        return len(self.items)

    def takesnapshot(self) -> None:
        """Take a snapshot of the current state of the queue.

        This method captures the current state of the queue and stores it in the
        snapshot attribute. The snapshot is a new instance of SimpleQueue with the
        same length and ID key, containing a copy of the current items.

        Args:
            None

        Returns:
            None

        Raises:
            None

        """
        self.snapshot = SimpleQueue(self.len, id_key=self.id_key)
        self.snapshot.items = self.items[:]

    def getsnapshot(self) -> "SimpleQueue | None":
        """Retrieve the snapshot of the queue.

        This method returns the snapshot of the queue, which is a previously captured
        state of the queue. If no snapshot has been taken, it returns None.

        Args:
            None

        Returns:
            The snapshot of the queue or None if no snapshot
                has been taken.

        Raises:
            None

        """
        return self.snapshot

    def get(self) -> list:
        """Get a copy of the current items in the queue.

        This method returns a copy of the current items in the queue.

        Args:
            None

        Returns:
            A copy of the current items in the queue.

        Raises:
            None

        """
        return self.items[:]

    def get_last_x(self, count: int) -> list:
        """Get the last X items from the queue.

        This method returns the last X items from the queue, where X is specified
        by the count parameter.

        Args:
            count: The number of items to retrieve from the end of the queue.

        Returns:
            A list containing the last X items from the queue.

        Raises:
            ValueError: If count is negative.

        """
        if count < 0:
            raise ValueError("Count must be non-negative")
        return self.items[-count:]

    def get_by_id(self, item_id: str) -> Any:
        """Retrieve an item by its ID.

        This method searches for and returns an item from the queue based on its ID.
        The ID is determined by the id_key provided during initialization. If no
        item with the specified ID is found, it returns None.

        Args:
            item_id: The ID of the item to retrieve.

        Returns:
            The item with the specified ID, or None if no such item is found.

        Raises:
            None

        """
        if self.id_key:
            for item in self.items:
                if item[self.id_key] == item_id:
                    return item

        return None

    def __len__(self) -> int:
        """Retrieve the number of items in the queue.

        This method returns the number of items currently in the queue, which allows
        the use of the len() function on an instance of SimpleQueue.

        Args:
            None

        Returns:
            The number of items in the queue.

        Raises:
            None

        """
        return len(self.items)

    def __iter__(self) -> Iterator[Any]:
        """Return an iterator for the queue.

        This method returns an iterator for the items in the queue, allowing for
        iteration over the queue's contents.

        Args:
            None

        Returns:
            An iterator for the items in the queue.

        Raises:
            None

        """
        return iter(self.items)
