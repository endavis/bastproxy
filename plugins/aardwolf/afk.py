"""
This plugin holds a afk plugin
"""
from __future__ import print_function
import time
import re
import copy
import libs.argp as argp
from plugins.aardwolf._aardwolfbaseplugin import AardwolfBasePlugin

NAME = 'AFK plugin'
SNAME = 'afk'
PURPOSE = 'do actions when no clients are connected'
AUTHOR = 'Bast'
VERSION = 1

TITLEMATCH = r'^Your title is: (?P<title>.*)\.$'
TITLERE = re.compile(TITLEMATCH)

TITLESETMATCH = r'Title now set to: (?P<title>.*)$'
TITLESET = re.compile(TITLESETMATCH)

class Plugin(AardwolfBasePlugin):
  """
  a plugin to show connection information
  """
  def __init__(self, *args, **kwargs):
    """
    initialize the instance
    """
    AardwolfBasePlugin.__init__(self, *args, **kwargs)

    self.temptitle = ''

    self.api('dependency.add')('aardwolf.connect')

  def initialize(self):
    """
    initialize the plugin
    """
    AardwolfBasePlugin.initialize(self)

    self.api('setting.add')('afktitle', 'is AFK.', str,
                            'the title when afk mode is enabled')
    self.api('setting.add')('lasttitle', '', str,
                            'the title before afk mode is enabled')
    self.api('setting.add')('queue', [], list, 'the tell queue',
                            readonly=True)
    self.api('setting.add')('isafk', False, bool, 'AFK flag',
                            readonly=True)

    parser = argp.ArgumentParser(add_help=False,
                                 description='show the communication queue')
    self.api('commands.add')('show', self.cmd_show,
                             parser=parser)

    parser = argp.ArgumentParser(add_help=False,
                                 description='clear the communication queue')
    self.api('commands.add')('clear', self.cmd_clear,
                             parser=parser)

    parser = argp.ArgumentParser(add_help=False,
                                 description='toggle afk')
    self.api('commands.add')('toggle', self.cmd_toggle,
                             parser=parser)

    self.api('watch.add')('titleset', '^(tit|titl|title) (?P<title>.*)$')

    self.api('events.register')('client_connected', self.clientconnected)
    self.api('events.register')('client_disconnected',
                                self.clientdisconnected)
    self.api('events.register')('watch_titleset', self._titlesetevent)

    self.api('setting.change')('isafk', False)
    self.api('events.register')('var_%s_isafk' % self.short_name, self._isafk_changeevent)

  def _isafk_changeevent(self, args=None): # pylint: disable=unused-argument
    """
    do something after afk has been changed
    """
    afkflag = self.api('setting.gets')('isafk')
    if afkflag:
      self.enableafk()
    else:
      self.disableafk()

  def after_first_active(self, _=None):
    """
    set the title when we first connect
    """
    AardwolfBasePlugin.after_first_active(self)
    if self.api('setting.gets')('lasttitle'):
      title = self.api('setting.gets')('lasttitle')
      self.api('send.execute')('title %s' % title)

  def _titlesetevent(self, args):
    """
    check for stuff when the title command is seen
    """
    self.api('send.msg')('saw title set command %s' % args)
    self.temptitle = args['title']
    self.api('events.register')('trigger_all', self.titlesetline)

  def titlesetline(self, args):
    """
    get the titleline
    """
    line = args['line'].strip()
    tmatch = TITLESET.match(line)
    if line:
      if tmatch:
        newtitle = tmatch.groupdict()['title']
        if newtitle != self.api('setting.gets')('afktitle'):
          self.api('setting.change')('lasttitle', self.temptitle)
          self.api('send.msg')('lasttitle is "%s"' % self.temptitle)
      else:
        self.api('send.msg')('unregistering trigger_all from titlesetline')
        self.api('events.unregister')('trigger_all', self.titlesetline)

  def cmd_show(self, _=None):
    """
    @G%(name)s@w - @B%(cmdname)s@w
      show the tell queue
      @CUsage@w: show
    """
    msg = []
    queue = self.api('setting.gets')('queue')
    if queue:
      msg.append('The queue is empty')
    else:
      msg.append('Tells received while afk')
      for i in queue:
        msg.append('%25s - %s' % (i['timestamp'], i['msg']))

    return True, msg

  def cmd_clear(self, _=None):
    """
    @G%(name)s@w - @B%(cmdname)s@w
      Show examples of how to use colors
      @CUsage@w: example
    """
    msg = []
    msg.append('AFK comm queue cleared')
    self.api('setting.change')('queue', [])
    self.savestate()
    return True, msg

  def cmd_toggle(self, _=None):
    """
    @G%(name)s@w - @B%(cmdname)s@w
      toggle afk mode
      @CUsage@w: toggle
    """
    msg = []
    newafk = not self.api('setting.gets')('isafk')
    self.api('setting.change')('isafk', newafk)

    return True, msg

  def checkfortell(self, args):
    """
    check for tells
    """
    print('checkfortell: %s' % args)
    if args['data']['chan'] == 'tell':
      print('found tell')
      tdata = copy.deepcopy(args['data'])
      tdata['timestamp'] = \
              time.strftime('%a %b %d %Y %H:%M:%S', time.localtime())
      queue = self.api('setting.gets')('queue')
      queue.append(tdata)
      self.savestate()

  def enableafk(self):
    """
    enable afk mode
    """
    afktitle = self.api('setting.gets')('afktitle')
    self.api('events.register')('GMCP:comm.channel', self.checkfortell)
    self.api('send.execute')('title %s' % afktitle)

  def disableafk(self):
    """
    disable afk mode
    """
    mud = self.api('managers.getm')('mud')
    if mud and mud.connected:
      lasttitle = self.api('setting.gets')('lasttitle')
      self.api('send.execute')('title %s' % lasttitle)
      try:
        self.api('events.unregister')('GMCP:comm.channel', self.checkfortell)
      except KeyError:
        pass

    queue = self.api('setting.gets')('queue')

    if queue:
      self.api('send.client')("@BAFK Queue")
      self.api('send.client')("@BYou have %s tells in the queue" % \
                len(queue))

  def clientconnected(self, _):
    """
    if we have enabled triggers when there were no clients, disable them
    """
    if self.api('clients.numconnected')() > 0:
      self.api('send.msg')('disabling afk mode')
      self.api('setting.change')('isafk', False)

  def clientdisconnected(self, _):
    """
    if this is the last client, enable afk triggers
    """
    if self.api('clients.numconnected')() == 0:
      self.api('send.msg')('enabling afk mode')
      self.api('setting.change')('isafk', True)
