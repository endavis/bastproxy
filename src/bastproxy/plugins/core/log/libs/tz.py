# Project: bastproxy
# Filename: plugins/core/log/libs/tz.py
#
# File Description: functions to change tzinfo in logging
#
# By: Bast
"""This module has functions for changing the timezone information in the logging module."""

# Standard Library
import datetime
import logging

# Third Party

# Project


def format_time_rfc3339_utc(
    self: logging.Formatter, record: logging.LogRecord, _datefmt: str | None = None
) -> str:
    """Formats a timestamp in the RFC3339 format in the UTC timezone.

    Args:
        self: The formatter instance (required by logging API).
        record: The record object containing the timestamp.
        _datefmt: Not used, but required by the logging module.

    Returns:
        str: The formatted timestamp in RFC3339 format with UTC timezone.

    """
    return datetime.datetime.fromtimestamp(record.created).astimezone(datetime.UTC).isoformat()


def format_time_rfc3339(
    self: logging.Formatter, record: logging.LogRecord, _datefmt: str | None = None
) -> str:
    """Formats a timestamp in the RFC3339 format in the local timezone.

    Args:
        self: The formatter instance (required by logging API).
        record: The record object containing the timestamp.
        _datefmt: Not used, but required by the logging module.

    Returns:
        str: The formatted timestamp in RFC3339 format.

    """
    return datetime.datetime.fromtimestamp(record.created).astimezone().isoformat()
