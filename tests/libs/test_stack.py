# Project: bastproxy
# Filename: tests/libs/test_stack.py
#
# File Description: Tests for Stack implementation
#
# By: Bast
"""Unit tests for the Stack class.

This module contains tests for the stack data structure.

"""

import pytest
from bastproxy.libs.stack import SimpleStack as Stack


class TestStack:
    """Test suite for Stack class."""

    def test_create_empty_stack(self) -> None:
        """Test creating an empty stack."""

        s: Stack = Stack()
        assert s.size() == 0
        assert s.isempty()

    def test_push_pop(self) -> None:
        """Test basic push and pop operations."""

        s: Stack = Stack()

        s.push("item1")
        assert s.size() == 1
        assert not s.isempty()

        item = s.pop()
        assert item == "item1"
        assert s.size() == 0
        assert s.isempty()

    def test_lifo_order(self) -> None:
        """Test that stack maintains LIFO order."""

        s: Stack = Stack()

        s.push("first")
        s.push("second")
        s.push("third")

        assert s.pop() == "third"
        assert s.pop() == "second"
        assert s.pop() == "first"

    def test_peek(self) -> None:
        """Test peeking at top element without removing."""

        s: Stack = Stack()

        s.push("item")
        peeked = s.peek()

        assert peeked == "item"
        assert s.size() == 1  # Item still in stack

    def test_peek_empty_returns_none(self) -> None:
        """Test that peeking at empty stack returns None."""

        s: Stack = Stack()

        assert s.peek() is None

    def test_size(self) -> None:
        """Test size() method."""

        s: Stack = Stack()

        assert s.size() == 0

        s.push("item1")
        s.push("item2")
        s.push("item3")

        assert s.size() == 3

    def test_getstack_returns_copy(self) -> None:
        """Test that getstack() returns a copy of stack items."""

        s: Stack = Stack()

        s.push("item1")
        s.push("item2")
        s.push("item3")

        items = s.getstack()
        assert items == ["item1", "item2", "item3"]
        assert s.size() == 3  # Original stack unchanged

    def test_remove_item(self) -> None:
        """Test removing a specific item from stack."""

        s: Stack = Stack()

        s.push("item1")
        s.push("item2")
        s.push("item3")

        s.remove("item2")
        assert s.size() == 2
        items = s.getstack()
        assert "item2" not in items

    def test_pop_empty_raises_error(self) -> None:
        """Test that popping from empty stack raises IndexError."""

        s: Stack = Stack()

        with pytest.raises(IndexError):
            s.pop()

    def test_remove_nonexistent_raises_error(self) -> None:
        """Test that removing nonexistent item raises ValueError."""

        s: Stack = Stack()

        s.push("item1")

        with pytest.raises(ValueError, match=r"list\.remove"):
            s.remove("nonexistent")

    def test_multiple_push_pop(self) -> None:
        """Test multiple push and pop operations."""

        s: Stack = Stack()

        # Push several items
        for i in range(10):
            s.push(f"item{i}")

        assert s.size() == 10

        # Pop them all and verify order
        for i in range(9, -1, -1):
            assert s.pop() == f"item{i}"

        assert s.isempty()

    def test_mixed_operations(self) -> None:
        """Test mixing push, pop, and peek operations."""

        s: Stack = Stack()

        s.push("first")
        assert s.peek() == "first"

        s.push("second")
        assert s.peek() == "second"

        popped = s.pop()
        assert popped == "second"
        assert s.peek() == "first"

        s.push("third")
        assert s.size() == 2
        assert s.pop() == "third"
        assert s.pop() == "first"
        assert s.isempty()

    def test_snapshot(self) -> None:
        """Test snapshot functionality."""

        s: Stack = Stack()

        s.push("item1")
        s.push("item2")
        s.takesnapshot()

        s.push("item3")

        snapshot = s.getsnapshot()
        assert snapshot is not None
        assert snapshot.size() == 2
        assert snapshot.pop() == "item2"
        assert snapshot.pop() == "item1"

    def test_fixed_length_stack(self) -> None:
        """Test stack with fixed length removes oldest items."""

        s: Stack = Stack(length=3)

        s.push("item1")
        s.push("item2")
        s.push("item3")
        assert s.size() == 3

        # Adding fourth item should remove first item
        s.push("item4")
        assert s.size() == 3
        items = s.getstack()
        assert items == ["item2", "item3", "item4"]  # item1 was removed

    def test_get_by_id(self) -> None:
        """Test getting items by ID when id_key is set."""

        s: Stack = Stack(id_key="id")

        s.push({"id": "1", "value": "first"})
        s.push({"id": "2", "value": "second"})
        s.push({"id": "3", "value": "third"})

        item = s.get_by_id("2")
        assert item is not None
        assert item["value"] == "second"

        # Test non-existent ID
        assert s.get_by_id("99") is None

    def test_get_by_id_no_id_key(self) -> None:
        """Test get_by_id returns None when no id_key is set."""

        s: Stack = Stack()

        s.push({"id": "1", "value": "test"})

        assert s.get_by_id("1") is None
