# Project: bastproxy
# Filename: libs/records/managers/updates.py
#
# File Description: a manager to manage updates to records
#
# By: Bast
"""
This module holds a manager to manage updates to records
"""
# Standard Library
from collections import deque

# 3rd Party

# Project


class UpdateManager(deque):
    """
    a class to manage changes to records

    each record instance will have one of these
    """
    def __init__(self):
        super().__init__(maxlen=1000)
        self.uid_mapping = {}

    def add(self, update):
        self.append(update)
        self.uid_mapping[update.uuid] = update

    def get_update(self, uuid):
        return self.uid_mapping.get(uuid, None)
