# -*- coding: utf-8 -*-
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
from libs.queue import Queue


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

    def test_peek(self) -> None:
        """Test peeking at front element without removing."""
        q: Queue = Queue()

        q.enqueue("item")
        peeked = q.peek()

        assert peeked == "item"
        assert len(q) == 1  # Item still in queue

    def test_clear(self) -> None:
        """Test clearing all items from queue."""
        q: Queue = Queue()

        q.enqueue("item1")
        q.enqueue("item2")
        q.clear()

        assert len(q) == 0
        assert q.isempty()
