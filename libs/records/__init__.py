# -*- coding: utf-8 -*-
# Project: bastproxy
# Filename: libs/records/__init__.py
#
# File Description: a "package" to manage records
#
# By: Bast
"""
This "package"" has classes for various record types and record managers
The public record types ones are:
    ToClientData - send data to the client
    NetworkData - build data to send
    LogRecord - data to log
    ToMudData - data to send to the mud
    EventArgsRecord - data to send to event callbacks

The public manager is RMANAGER, which manages records or all types

There are also some private classes that are used to manage records
    BaseRecord - the base class for all records
    ChangeRecord - a record that holds a change to a record
    ChangeManager - a manager that manages changes to records
"""
__all__ = ['LogRecord', 'BaseDictRecord', 'BaseRecord',
           'RMANAGER', 'CmdArgsRecord',
           'NetworkDataLine',
           'NetworkData', 'ToClientData', 'ToMudData']

from libs.records.rtypes.base import BaseRecord, BaseDictRecord # import to resolve circular import
from libs.records.rtypes.clientdata import ToClientData
from libs.records.rtypes.log import LogRecord
from libs.records.rtypes.cmdargs import CmdArgsRecord
from libs.records.managers.records import RMANAGER
from libs.records.rtypes.networkdata import NetworkDataLine, NetworkData
from libs.records.rtypes.muddata import ToMudData









