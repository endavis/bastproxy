# Project: bastproxy
# Filename: tests/libs/test_queue.py
#
# File Description: Tests for Queue implementation
#
# By: Bast
"""Unit tests for the Queue class.

This module contains tests for the queue data structure.

"""

import pytest
from bastproxy.libs.queue import SimpleQueue as Queue


class TestQueue:
    """Test suite for Queue class."""

    def test_create_empty_queue(self) -> None:
        """Test creating an empty queue."""

        q: Queue = Queue()
        assert len(q) == 0
        assert q.isempty()

    def test_enqueue_dequeue(self) -> None:
        """Test basic enqueue and dequeue operations."""

        q: Queue = Queue()

        q.enqueue("item1")
        assert len(q) == 1
        assert not q.isempty()

        item = q.dequeue()
        assert item == "item1"
        assert len(q) == 0
        assert q.isempty()

    def test_fifo_order(self) -> None:
        """Test that queue maintains FIFO order."""

        q: Queue = Queue()

        q.enqueue("first")
        q.enqueue("second")
        q.enqueue("third")

        assert q.dequeue() == "first"
        assert q.dequeue() == "second"
        assert q.dequeue() == "third"

    def test_queue_length_tracking(self) -> None:
        """Test that len() works via __len__ dunder method."""

        q: Queue = Queue()

        assert len(q) == 0

        q.enqueue("first")
        q.enqueue("second")
        assert len(q) == 2

        q.dequeue()
        assert len(q) == 1

    def test_iteration_support(self) -> None:
        """Test iteration via __iter__ dunder method."""

        q: Queue = Queue()

        q.enqueue("first")
        q.enqueue("second")
        q.enqueue("third")

        items = list(q)
        assert items == ["first", "second", "third"]

    def test_fixed_length_queue(self) -> None:
        """Test queue with fixed length removes oldest items."""

        q: Queue = Queue(length=3)

        q.enqueue("item1")
        q.enqueue("item2")
        q.enqueue("item3")
        assert len(q) == 3

        # Adding fourth item should remove first item
        q.enqueue("item4")
        assert len(q) == 3
        assert q.dequeue() == "item2"  # item1 was removed

    def test_snapshot(self) -> None:
        """Test snapshot functionality."""

        q: Queue = Queue()

        q.enqueue("item1")
        q.enqueue("item2")
        q.takesnapshot()

        q.enqueue("item3")

        snapshot = q.getsnapshot()
        assert snapshot is not None
        assert len(snapshot) == 2
        assert snapshot.dequeue() == "item1"
        assert snapshot.dequeue() == "item2"

    def test_get_returns_copy(self) -> None:
        """Test that get() returns a copy of items."""

        q: Queue = Queue()

        q.enqueue("item1")
        q.enqueue("item2")

        items = q.get()
        assert len(items) == 2
        assert items == ["item1", "item2"]
        assert len(q) == 2  # Original queue unchanged

    def test_get_last_x(self) -> None:
        """Test getting last X items."""

        q: Queue = Queue()

        q.enqueue("item1")
        q.enqueue("item2")
        q.enqueue("item3")
        q.enqueue("item4")

        last_two = q.get_last_x(2)
        assert len(last_two) == 2
        assert last_two == ["item3", "item4"]

    def test_get_by_id(self) -> None:
        """Test retrieving items by ID."""

        q: Queue = Queue(id_key="id")

        item1 = {"id": "abc", "data": "test1"}
        item2 = {"id": "def", "data": "test2"}

        q.enqueue(item1)
        q.enqueue(item2)

        found = q.get_by_id("def")
        assert found == item2

    def test_get_by_id_not_found(self) -> None:
        """Test get_by_id returns None for missing ID."""

        q: Queue = Queue(id_key="id")

        item = {"id": "abc", "data": "test"}
        q.enqueue(item)

        found = q.get_by_id("xyz")
        assert found is None

    def test_iterator(self) -> None:
        """Test that queue can be iterated."""

        q: Queue = Queue()

        q.enqueue("item1")
        q.enqueue("item2")
        q.enqueue("item3")

        items = list(q)
        assert items == ["item1", "item2", "item3"]

    def test_size_method(self) -> None:
        """Test size() method."""

        q: Queue = Queue()

        assert q.size() == 0

        q.enqueue("item1")
        q.enqueue("item2")

        assert q.size() == 2

    def test_dequeue_empty_raises_error(self) -> None:
        """Test that dequeuing from empty queue raises IndexError."""

        q: Queue = Queue()

        with pytest.raises(IndexError):
            q.dequeue()

    def test_get_last_x_negative_count(self) -> None:
        """Test that get_last_x with negative count raises ValueError."""

        q: Queue = Queue()

        q.enqueue("item1")

        with pytest.raises(ValueError, match="Count must be non-negative"):
            q.get_last_x(-1)
