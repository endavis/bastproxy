# -*- coding: utf-8 -*-
# Project: bastproxy
# Filename: libs/stack.py
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


class SimpleStack(object):
    """
    a simple queue class
    """
    def __init__(self, length=10, id_key=None):
        """
        initialize the class

        length is the length of the stack
        id_field is the dictionary key to use for id lookups
        """
        self.len = length
        self.items = []
        self.snapshot = None
        self.id_key = id_key
        self.id_lookup = {}

    def isempty(self) -> bool:
        """
        return True for an empty stack
        """
        return self.items == []

    def push(self, item):
        """
        push an item
        """
        self.items.append(item)
        while len(self.items) > self.len:
            self.items.pop(0)

    def pop(self):
        """
        pop an item
        """
        return self.items.pop()

    def peek(self):
        """
        peek at the top of the stack
        """
        return self.items[-1] if len(self.items) > 0 else None

    def size(self):
        """
        return the size of the stack
        """
        return len(self.items)

    def takesnapshot(self):
        """
        take a snapshot of the current stack
        """
        self.snapshot = SimpleStack(self.len, id_key=self.id_key)
        self.snapshot.items = self.items[:]

    def getstack(self) -> list:
        """
        return the current stack

        returns a copy of the item list
        """
        return self.items[:]

    def getsnapshot(self):
        """
        return the current snapshot
        """
        return self.snapshot

    def get_by_id(self, item_id):
        """
        get an item by id
        """
        if self.id_key:
            for item in self.items:
                if item[self.id_key] == item_id:
                    return item

        return None
