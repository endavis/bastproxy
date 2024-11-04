# -*- coding: utf-8 -*-
# Project: bastproxy
# Filename: libs/queue.py
#
# File Description: a simple queue class
#
# By: Bast
"""
This plugin has a simple queue class
"""
# Standard Library

# 3rd Party

# Project


class SimpleQueue(object):
    """
    a simple queue class
    """
    def __init__(self, length=10, id_key=None):
        """
        initialize the class

        length is the length of the queue
        id_field is the dictionary key to use for id lookups
        """
        self.len = length
        self.items: list = []
        self.snapshot = None
        self.id_key = id_key
        self.id_lookup = {}
        self.last_automatically_removed_item = None

    def isempty(self):
        """
        return True for an empty queue
        """
        return self.items == []

    def enqueue(self, item):
        """
        queue an item
        """
        self.items.append(item)
        while len(self.items) > self.len:
            self.last_automatically_removed_item = self.items.pop(0)

    def dequeue(self):
        """
        dequeue an item
        """
        return self.items.pop(0)

    def size(self):
        """
        return the size of the queue
        """
        return len(self.items)

    def takesnapshot(self):
        """
        take a snapshot of the current queue
        """
        self.snapshot = SimpleQueue(self.len, id_key=self.id_key)
        self.snapshot.items = self.items[:]

    def getsnapshot(self):
        """
        return the current snapshot
        """
        return self.snapshot

    def get(self) -> list:
        """
        return the current stack

        returns a copy of the item list
        """
        return self.items[:]

    def get_last_x(self, count):
        """
        get the last x items in the queue
        """
        return self.items[-count:]

    def get_by_id(self, item_id):
        """
        get an item by id
        """
        if self.id_key:
            for item in self.items:
                if item[self.id_key] == item_id:
                    return item

        return None

    def __len__(self):
        return len(self.items)

    def __iter__(self):
        return iter(self.items)
