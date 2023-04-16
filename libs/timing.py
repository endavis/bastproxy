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
    tname = f"{func.func_name}"
    TIMING.starttimer(tname, arg)
    res = func(*arg)
    TIMING.finishtimer(tname, arg)
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
    if tbool is None:
      self.enabled = not self.enabled
    else:
      self.enabled = bool(tbool)

  def starttimer(self, timername, args=None):
    """
    start a timer
    """
    if self.enabled:
      owner_id = self.api('libs.api:get.caller.owner')()
      self.timing[timername] = {}
      self.timing[timername]['start'] = default_timer()
      self.timing[timername]['owner_id'] = owner_id
      LogRecord(f"starttimer - {timername:<20} : started - from {owner_id} with args {args}",
                level='debug', sources=[__name__, owner_id]).send()

  def finishtimer(self, timername, args=None):
    """
    finish a timer
    """
    if self.enabled:
      timerfinish = default_timer()
      if timername in self.timing:
        LogRecord(f"finishtimer - {timername:<20} : finished in {(timerfinish - self.timing[timername]['start']) * 1000.0} ms - with args {args}",
                    level='debug', sources=[__name__, self.timing[timername]['owner_id']]).send()
        del self.timing[timername]
      else:
        owner_id = self.api('libs.api:get.caller.owner')()
        LogRecord(f"finishtimer - {timername:<20} : not found - called from {owner_id}",
                    level='error', sources=[__name__, owner_id]).send()

TIMING = Timing()
