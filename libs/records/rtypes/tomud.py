# -*- coding: utf-8 -*-
# Project: bastproxy
# Filename: libs/records/rtypes/tomud.py
#
# File Description: Holds the tomud record type
#
# By: Bast
"""
Holds the tomud record type
"""
# Standard Library

# 3rd Party

# Project
from libs.records.rtypes.base import BaseRecord

class ToMudRecord(BaseRecord):
    """
    a record to the mud, all client data will start as this type of record
    data from a client will be immediately transformed into this type of record
    this record will go through execute first
    it may not end up going to the mud depending on if it is a command
    """
    def __init__(self, message, internal=True):
        """
        initialize the class
        """
        super().__init__(message, internal)
