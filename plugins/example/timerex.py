"""
This plugin is an example plugin to show how to use timers
"""
from plugins._baseplugin import BasePlugin

NAME = 'Timer Example'
SNAME = 'timerex'
PURPOSE = 'examples for using timers'
AUTHOR = 'Bast'
VERSION = 1



class Plugin(BasePlugin):
  """
  a plugin to show how to use timers
  """
  def __init__(self, *args, **kwargs):
    """
    initialize the instance
    """
    BasePlugin.__init__(self, *args, **kwargs)

    self.api('dependency.add')('core.timers')

  def initialize(self):
    """
    initialize the plugin
    """
    BasePlugin.initialize(self)

    self.api('timers.add')('test_timer', self.test,
                           600, onetime=False)
    self.api('timers.add')('test_touser_timer', self.test_to_user,
                           10, onetime=True)
    self.api('timers.add')('test_timewsec', self.test_timewsec,
                           60, time='2010')
    self.api('timers.add')('test_time', self.test_time,
                           60*60*24, time='1200')

  def test(self):
    """
    send a message to the mud and client
    """
    self.api('send.client')(
        '@RHere is the timer that fires every 600 seconds!')
    self.api('send.execute')('look')

  def test_to_user(self):
    """
    test a onetime timer
    """
    self.api('send.client')('@RA onetime timer just fired.')

  def test_timewsec(self):
    """
    test an time timer with seconds
    """
    self.api('send.client')(
        'this is the timer that starts at 2010 and goes every 1 minute')

  def test_time(self):
    """
    test an time timer
    """
    self.api('send.client')(
        'this is the timer that fires at noon')
