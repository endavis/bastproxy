# -*- coding: utf-8 -*-
# Project: bastproxy
# Filename: libs/records/rtypes/log.py
#
# File Description: Holds the log record type
#
# By: Bast
"""
Holds the log record type
"""
# Standard Library
import logging
import typing

# 3rd Party

# Project
from libs.records.rtypes.base import BaseListRecord

class LogRecord(BaseListRecord):
    """
    a simple message record for logging, this may end up sent to a client
    """
    def __init__(self, message: list[str] | str, level: str='info', sources: list | None = None, **kwargs):
        """
        initialize the class
        """
        super().__init__(message, internal=True, track_record=False)
        # The type of message
        self.level: str = level
        # The sources of the message for logging purposes, a list
        self.sources: list[str] = sources or []
        self.kwargs = kwargs
        self.wasemitted: dict[str, bool] = {
            'console': False,
            'file': False,
            'client': False,
        }

    def color_lines(self, actor: str=''):
        """
        color the message

        actor is the item that ran the color function
        """
        if not self.api('libs.api:has')('plugins.core.log:get.level.color'):
            return
        color: str = self.api('plugins.core.log:get.level.color')(self.level)
        super().color_lines(color, actor)

    def add_source(self, source: str):
        """
        add a source to the message
        """
        if source not in self.sources:
            self.sources.append(source)

    def format(self, actor: str=''):
        self.clean(actor)
        self.color_lines(actor)

    def _exec_(self, actor: str=''):
        """
        send the message to the logger
        """
        self.format(actor)
        add_log_count_func: typing.Callable | None = None
        if self.api('libs.api:has')('plugins.core.log:add.log.count'):
            add_log_count_func = self.api('plugins.core.log:add.log.count')
        for i in self.sources:
            if i:
                if add_log_count_func:
                    add_log_count_func(i, self.level)
                try:
                    logger = logging.getLogger(i)
                    loggingfunc = getattr(logger, self.level)
                    loggingfunc(self, **self.kwargs)
                except TypeError:
                    LogRecord(f"LogRecord.send: logger name is not a string, {i}",
                              level='error', sources=[__name__], exc_info=True)()

    def __str__(self):
        """
        return the message as a string
        """
        return '\n'.join(self.data)
