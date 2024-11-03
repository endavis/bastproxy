# -*- coding: utf-8 -*-
# Project: bastproxy
# Filename: libs/timing.py
#
# File Description: a module to time functions
#
# By: Bast
"""
this module is for timing functions
"""
# Standard Library
from functools import wraps
from timeit import default_timer
from uuid import uuid4

# 3rd Party

# Project
from libs.api import API as BASEAPI
from libs.api import AddAPI
from libs.records import LogRecord

API = BASEAPI(owner_id=__name__)


def duration(func):
    """
    a decorator to find the duration of a function
    """
    @wraps(func)
    def wrapper(*arg):
        """
        the wrapper to find the duration of a function
        """
        tname = f"{func.func_name}"
        uid = API('libs.timing:start')(tname, arg)
        res = func(*arg)
        API('libs.timing:finish')(uid)
        return res
    return wrapper

class Timing(object):
    """
    manage timing functions
    """
    def __init__(self):
        """
        create the dictionary
        """
        self.api = API
        self.enabled = True

        self.timing = {}

        self.api('libs.api:add.apis.for.object')(__name__, self)

    @AddAPI('toggle', description='toggle the enabled flag')
    def _api_toggle(self, tbool=None):
        """
        toggle the timing flag
        """
        self.enabled = not self.enabled if tbool is None else bool(tbool)

    @AddAPI('start', description='start a timer')
    def _api_start(self, timername='', args=None):
        """
        start a timer
        """
        uid = uuid4().hex
        if self.enabled:
            owner_id = self.api('libs.api:get.caller.owner')()
            self.timing[uid] = {'name': timername, 'start': default_timer(),
                                'owner_id': owner_id, 'args': args}
            LogRecord(f"starttimer - {uid} {timername:<20} : started - from {owner_id} with args {args}",
                      level='debug', sources=[__name__, owner_id])()
            return uid
        return None

    @AddAPI('finish', description='finish a timer')
    def _api_finish(self, uid):
        """
        finish a timer
        """
        if self.enabled:
            timerfinish = default_timer()
            if uid in self.timing:
                timername = self.timing[uid]['name']
                time_taken = (timerfinish - self.timing[uid]['start']) * 1000.0
                if args := self.timing[uid]['args']:
                    LogRecord(f"finishtimer - {uid} {timername:<20} : finished in {time_taken} ms - with args {args}",
                            level='debug', sources=[__name__, self.timing[uid]['owner_id']])()
                else:
                    LogRecord(f"finishtimer - {uid} {timername:<20} : finished in {time_taken} ms",
                            level='debug', sources=[__name__, self.timing[uid]['owner_id']])()
                del self.timing[uid]
                return time_taken
            else:
                owner_id = self.api('libs.api:get.caller.owner')()
                LogRecord(f"finishtimer - {uid} not found - called from {owner_id}",
                            level='error', sources=[__name__, owner_id])()
        return None

TIMING = Timing()
