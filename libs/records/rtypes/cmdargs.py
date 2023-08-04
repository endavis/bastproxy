# -*- coding: utf-8 -*-
# Project: bastproxy
# Filename: libs/records/rtypes/cmdargs.py
#
# File Description: Holds the record type for command arguments
#
# By: Bast
"""
Holds the log record type
"""
# Standard Library

# 3rd Party

# Project
from libs.records.rtypes.base import BaseDictRecord

class CmdArgsRecord(BaseDictRecord):
    def __init__(self, owner_id: str = '', data: dict | None = None, arg_string: str = ''):
        """
        initialize the class
        """
        BaseDictRecord.__init__(self, owner_id, data, track_record=False)
        self.arg_string: str = arg_string

    def get_attributes_to_format(self):
        attributes = super().get_attributes_to_format()
        attributes[0].append(('Arg String', 'arg_string'))
        return attributes
