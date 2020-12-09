"""
This plugin adds events for Aardwolf Ice Ages.
"""
import time
import libs.argp as argp
from plugins.aardwolf._aardwolfbaseplugin import AardwolfBasePlugin

NAME = 'Aardwolf Daily blessing'
SNAME = 'daily'
PURPOSE = 'Send event when daily blessing is available'
AUTHOR = 'Bast'
VERSION = 1



class Plugin(AardwolfBasePlugin):
  """
  a plugin to handle aardwolf quest events
  """
  def __init__(self, *args, **kwargs):
    """
    initialize the instance
    """
    AardwolfBasePlugin.__init__(self, *args, **kwargs)

    self.seconds = -1
    self.nextdaily = -1

  def initialize(self):
    """
    initialize the plugin
    """
    AardwolfBasePlugin.initialize(self)

    self.api('core.triggers:trigger:add')(
        'daily1',
        r"^You can receive a new daily blessing in (?P<hours>[\d]*) hour[s]*, " \
           r"(?P<minutes>[\d]*) minute[s]* and (?P<seconds>[\d]*) second[s]*.$")

    self.api('core.triggers:trigger:add')(
        'daily2',
        r"^You can receive a new daily blessing in (?P<minutes>[\d]*) minute[s]* " \
           r"and (?P<seconds>[\d]*) second[s]*.$")

    self.api('core.triggers:trigger:add')(
        'daily3',
        r"^You can receive a new daily blessing in (?P<seconds>[\d]*) second[s]*.$")

    self.api('core.triggers:trigger:add')(
        'dailynow',
        "^You are ready to receive a new daily blessing.$")

    self.api('core.triggers:trigger:add')(
        'tookdaily',
        "^You bow your head to Ayla and receive your daily blessing.$")

    parser = argp.ArgumentParser(add_help=False,
                                 description='show next daily')
    self.api('core.commands:command:add')('next', self.cmd_next,
                                          parser=parser)

    self.api('core.events:register:to:event')('trigger_daily1', self.dailytime)
    self.api('core.events:register:to:event')('trigger_daily2', self.dailytime)
    self.api('core.events:register:to:event')('trigger_daily3', self.dailytime)
    self.api('core.events:register:to:event')('trigger_tookdaily', self.tookdaily)
    self.api('core.events:register:to:event')('trigger_dailynow', self.dailyavailable)

    self.checkdaily()

  def cmd_next(self, _=None):
    """
    show nex daily
    """
    msg = []

    if self.nextdaily != -1:
      ntime = time.localtime(self.nextdaily)
      msg.append('Your next daily is at: ' + \
        time.strftime('%a, %d %b %Y %H:%M:%S', ntime))
    else:
      msg.append('Please type daily to update plugin')

    return True, msg

  def dailytime(self, args):
    """
    saw the message about daily time
    """
    hours = 0
    minutes = 0
    seconds = 0
    if 'hours' in args:
      hours = int(args['hours'])

    if 'minutes' in args:
      minutes = int(args['minutes'])

    if 'seconds' in args:
      seconds = int(args['seconds'])

    self.seconds = hours * 60 * 60 + minutes * 60 + seconds

    self.nextdaily = time.time() + self.seconds

    self.updatedaily()

  def tookdaily(self, _=None):
    """
    took a daily
    """
    self.seconds = 23 * 60 * 60
    self.nextdaily = time.time() + self.seconds

    self.updatedaily()

  def updatedaily(self, _=None):
    """
    update the daily timer
    """
    self.api('libs.io:send:msg')('updating daily blessing timer')
    self.api('core.timers:remove:timer')('dailyblessing')
    self.api('core.timers:add:timer')('dailyblessing', self.dailyavailable,
                                      self.seconds, onetime=True)

  def dailyavailable(self, _=None):
    """
    send a daily available event
    """
    self.api('core.timers:remove:timer')('dailyblessing')
    self.api('core.events:raise:event')('aard_daily_available')

  def after_first_active(self, _=None):
    """
    do something on connect
    """
    AardwolfBasePlugin.after_first_active(self)

    self.checkdaily()

  def checkdaily(self):
    """
    check to see if daily has been seen
    """
    if self.nextdaily == -1:
      state = self.api('net.GMCP:value:get')('char.status.state')
      if state == 3:
        self.api('libs.io:send:execute')('daily')
