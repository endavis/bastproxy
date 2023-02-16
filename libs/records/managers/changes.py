# -*- coding: utf-8 -*-
# Project: bastproxy
# Filename: libs/records/managers/changes.py
#
# File Description: a manager to manage changes to records
#
# By: Bast
"""
This module holds a manager to manage changes to records
"""
# Standard Library
from collections import deque

# 3rd Party

# Project


class ChangeManager(object):
    """
    a class to manage changes to records

    each record instance will have one of these
    """
    def __init__(self):
        self.changes = deque(maxlen=1000)

    def add(self, change):
        self.changes.append(change)
