# Project: bastproxy
# Filename: tests/libs/test_stack.py
#
# File Description: Tests for Stack implementation
#
# By: Bast
"""Unit tests for the Stack class.

This module contains tests for the stack data structure.

"""
from libs.stack import Stack


class TestStack:
    """Test suite for Stack class."""

    def test_create_empty_stack(self) -> None:
        """Test creating an empty stack."""
        s: Stack = Stack()
        assert len(s) == 0
        assert s.isempty()

    def test_push_pop(self) -> None:
        """Test basic push and pop operations."""
        s: Stack = Stack()

        s.push("item1")
        assert len(s) == 1
        assert not s.isempty()

        item = s.pop()
        assert item == "item1"
        assert len(s) == 0
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
        assert len(s) == 1  # Item still in stack

    def test_clear(self) -> None:
        """Test clearing all items from stack."""
        s: Stack = Stack()

        s.push("item1")
        s.push("item2")
        s.clear()

        assert len(s) == 0
        assert s.isempty()
