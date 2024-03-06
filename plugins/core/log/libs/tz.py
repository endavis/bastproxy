# -*- coding: utf-8 -*-
# Project: bastproxy
# Filename: plugins/core/log/libs/tz.py
#
# File Description: functions to change tzinfo in logging
#
# By: Bast
"""
This module has functions for changing the timezone information in the logging module.
"""
# Standard Library
import datetime

# Third Party

# Project


def formatTime_RFC3339_UTC(self, record, datefmt=None):
    """
    Formats a timestamp in the RFC3339 format in the UTC timezone.

    Args:
        record: The record object containing the timestamp.
        datefmt: Not used, but required by the logging module.

    Returns:
        str: The formatted timestamp in RFC3339 format with UTC timezone.
    """
    return (
        datetime.datetime.fromtimestamp(record.created)
        .astimezone(datetime.timezone.utc)
        .isoformat()
    )

def formatTime_RFC3339(self, record, datefmt=None):
    """
    Formats a timestamp in the RFC3339 format in the local timezone.

    Args:
        record: The record object containing the timestamp.
        datefmt: Not used, but required by the logging module.

    Returns:
        str: The formatted timestamp in RFC3339 format.
    """
    return (
        datetime.datetime.fromtimestamp(record.created)
        .astimezone()
        .isoformat()
    )
