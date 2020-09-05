"""
this module is for timing functions
"""
from timeit import default_timer
from libs.api import API as BASEAPI
API = BASEAPI()

def duration(func):
  """
  a decorator to find the duration of a function
  """
  def wrapper(*arg):
    """
    the wrapper to find the duration of a function
    """
    tname = '%s' % (func.func_name)
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

    self.api('api:add')('timep', 'start', self.starttimer)
    self.api('api:add')('timep', 'finish', self.finishtimer)
    self.api('api:add')('timep', 'toggle', self.toggletiming)

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
      plugin = self.api('api:get:caller:plugin')()
      self.timing[timername] = {}
      self.timing[timername]['start'] = default_timer()
      self.timing[timername]['plugin'] = plugin
      self.api('send:msg')('%-20s : started - from plugin %s with args %s' % \
                            (timername, plugin, args),
                           primary=plugin, secondary=['timing'])

  def finishtimer(self, timername, args=None):
    """
    finish a timer
    """
    if self.enabled:
      timerfinish = default_timer()
      if timername in self.timing:
        self.api('send:msg')('%-20s : finished in %s ms - with args %s' % \
                             (timername,
                              (timerfinish - self.timing[timername]['start']) * 1000.0,
                              args),
                             primary=self.timing[timername]['plugin'],
                             secondary=['timing'])
        del self.timing[timername]
      else:
        plugin = self.api('api:get:caller:plugin')()
        self.api('send:error')('timername: %s not found, called from %s' % \
                              (timername, plugin),
                               secondary=['timing', plugin])

TIMING = Timing()
