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
    uid = uuid4().hex
    tname = f"{func.func_name}"
    TIMING.starttimer(uid, tname, arg)
    res = func(*arg)
    TIMING.finishtimer(uid, tname, arg)
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

    self.api('libs.api:add')('libs.timing', 'start', self.starttimer)
    self.api('libs.api:add')('libs.timing', 'finish', self.finishtimer)
    self.api('libs.api:add')('libs.timing', 'toggle', self.toggletiming)

  def toggletiming(self, tbool=None):
    """
    toggle the timing flag
    """
    self.enabled = not self.enabled if tbool is None else bool(tbool)

  def starttimer(self, uid, timername, args=None):
    """
    start a timer
    """
    if self.enabled:
      owner_id = self.api('libs.api:get.caller.owner')()
      self.timing[uid] = {'name': timername, 'start': default_timer(),
                          'owner_id': owner_id}
      LogRecord(f"starttimer - {uid} {timername:<20} : started - from {owner_id} with args {args}",
                level='debug', sources=[__name__, owner_id])()

  def finishtimer(self, uid, timername, args=None):
    """
    finish a timer
    """
    if self.enabled:
      timerfinish = default_timer()
      if uid in self.timing:
        LogRecord(f"finishtimer - {uid} {timername:<20} : finished in {(timerfinish - self.timing[uid]['start']) * 1000.0} ms - with args {args}",
                    level='debug', sources=[__name__, self.timing[uid]['owner_id']])()
        del self.timing[timername]
      else:
        owner_id = self.api('libs.api:get.caller.owner')()
        LogRecord(f"finishtimer - {uid} {timername:<20} : not found - called from {owner_id}",
                    level='error', sources=[__name__, owner_id])()

TIMING = Timing()
