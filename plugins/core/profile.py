"""
This plugin shows and clears errors seen during plugin execution
"""
from plugins._baseplugin import BasePlugin
import libs.argp as argp
from libs.queue import SimpleQueue

NAME = 'Profile Plugin'
SNAME = 'profile'
PURPOSE = 'profile functions and commands'
AUTHOR = 'Bast'
VERSION = 1
PRIORITY = 25

REQUIRED = True

class Plugin(BasePlugin):
  """
  a plugin to echo commands to the client that are sent to the mud
  """
  def __init__(self, *args, **kwargs):
    """
    initialize the instance
    """
    BasePlugin.__init__(self, *args, **kwargs)

    self.commandtraces = None
    self.changedmuddata = None

  def initialize(self):
    """
    initialize the plugin
    """
    BasePlugin.initialize(self)

    self.api('setting.add')('commands', False, bool,
                            'flag to echo commands')
    self.api('setting.add')('functions', False, bool,
                            'flag to profile functions')
    self.api('setting.add')('stacklen', 20, int,
                            '# of traces kept')
    self.api('setting.add')('cmdfuncstack', False, bool,
                            'print the function stack in an echo')

    parser = argp.ArgumentParser(
        add_help=False,
        description='show trace info about commands')
    parser.add_argument('-i', '--item',
                        help='the item to show',
                        default='',
                        nargs='?')
    parser.add_argument(
        '-c', "--callstack",
        help="print callstack if available",
        action="store_true",
        default=False)
    self.api('commands.add')('commands', self.cmd_commands,
                             parser=parser)

    parser = argp.ArgumentParser(
        add_help=False,
        description='show trace info about data from the mud')
    parser.add_argument('-i', '--item',
                        help='the item to show',
                        default='',
                        nargs='?')
    # parser.add_argument(
    #     '-c', "--callstack",
    #     help="print callstack if available",
    #     action="store_true",
    #     default=False)
    self.api('commands.add')('muddata', self.cmd_muddata,
                             parser=parser)

    parser = argp.ArgumentParser(add_help=False,
                                 description='reset command stack')
    self.api('commands.add')('rstack', self.cmd_rstack,
                             parser=parser)

    self.commandtraces = SimpleQueue(self.api('setting.gets')('stacklen'))
    self.changedmuddata = SimpleQueue(self.api('setting.gets')('stacklen'))

    self.api('events.register')('io_execute_trace_finished', self.savecommand, prio=99)
    self.api('events.register')('from_mud_event', self.savechangedmuddata, prio=99)
    self.api('events.register')('var_%s_functions' % self.short_name, self.onfunctionschange)

  def onfunctionschange(self, _=None):
    """
    toggle the function profiling
    """
    functions = self.api('setting.gets')('functions')
    self.api('timep.toggle')(functions)

  def listcommands(self):
    """
    list the command profiles that have been saved
    """
    tmsg = ['Command Traces:']
    for i in self.commandtraces.items:
      tmsg.append('  %s' % i['originalcommand'])
    return True, tmsg

  def listchangedmuddata(self):
    """
    list the muddata profiles that have been saved
    """
    self.changedmuddata.takesnapshot()
    items = self.changedmuddata.getsnapshot()
    tmsg = ['Data Traces:']

    for i in range(0, len(items)):
      tmsg.append('%-3s : %s' % (i, items[i]['trace']['original']))
    return True, tmsg

  def showchangedmuddata(self, item, callstack=False): # pylint: disable=unused-argument
    """
    find the changed muddata and print it
    """
    snapshot = self.changedmuddata.getsnapshot()
    if not snapshot:
      self.changedmuddata.takesnapshot()
      snapshot = self.changedmuddata.getsnapshot()

    try:
      titem = snapshot[item]
      return True, [self.formatmuddatastack(titem)]
    except IndexError:
      return False, ['Could not find item: %s' % item]

  def showcommand(self, item, callstack=False):
    """
    find the command trace and format it
    """
    for i in self.commandtraces.items:
      if i['originalcommand'].startswith(item):
        return True, [self.formatcommandstack(i, callstack)]

    return False, ['Could not find item: %s' % item]

  def cmd_commands(self, args=None):
    """
    get info for a command trace
    """
    if 'item' in args and args['item']:
      return self.showcommand(args['item'], callstack=args['callstack'])

    return self.listcommands()

  def cmd_muddata(self, args=None):
    """
    get info for a muddata trace
    """
    if 'item' in args and args['item']:
      return self.showchangedmuddata(int(args['item']), callstack=False)

    return self.listchangedmuddata()

  def cmd_rstack(self, _=None):
    """
    reset the command trace
    """
    iom = self.api('managers.getm')('io')

    msg = []
    msg.append('The following stack was active')
    msg.append('%s' % iom.currenttrace)
    iom.currenttrace = None
    msg.append('The stack has been reset')

    return True, msg

  def formatmuddatastack(self, stack):
    """
    format the command stack
    """
    msg = ['------------------- Muddata Trace -------------------']
    msg.append('%-17s : %s' % ('Original', stack['trace']['original']))

    msg.append('-------------- Internal Stack --------------')
    count = 0
    for i in stack['trace']['changes']:
      count = count + 1
      if 'plugin' in i and i['plugin']:
        apicall = '%s.formatmuddatatraceitem' % i['plugin']
        if self.api('api.has')(apicall):
          msg.append(self.api(apicall)(i))
          continue

      msg.append("%-2s - %-15s :   %s - %s" % (count, i['plugin'].capitalize(), i['flag'],
                                               i['data']))

    return '\n'.join(msg)

  def formatcommandstack(self, stack, callstack=False):
    """
    format the command stack
    """
    msg = ['------------------- Command Trace -------------------']
    msg.append('%-17s : %s' % ('Original', stack['originalcommand']))
    if stack['fromclient']:
      msg.append('%-17s : from client' % 'Originated')
    if stack['internal']:
      msg.append('%-17s : Internal' % 'Originated')
    if 'fromplugin' in stack and stack['fromplugin']:
      msg.append('%-17s : %s' % ('Plugin', stack['fromplugin']))
    msg.append('%-17s : %s' % ('Show in History', stack['showinhistory']))
    msg.append('%-17s : %s' % ('Added to History', stack['addedtohistory']))

    msg.append('-------------- Internal Stack --------------')
    count = 0
    for i in stack['changes']:
      count = count + 1
      if 'plugin' in i and i['plugin']:
        apicall = '%s.formatcmdtraceitem' % i['plugin']
        if self.api('api.has')(apicall):
          msg.append(self.api(apicall)(i))
          continue

      msg.append("%-2s - %-15s :   %s - %s" % (count, i['plugin'].capitalize(), i['flag'],
                                               i['data']))

      if callstack and 'callstack' in i:
        for line in i['callstack']:
          msg.append("%-20s :   %s" % ("", line))

    msg.append('-----------------------------------------------------')


    return '\n'.join(msg)

  def savecommand(self, args):
    """
    echo the command
    """
    self.commandtraces.enqueue(args)

    echocommands = self.api('setting.gets')('commands')

    if echocommands:
      self.api('send.client')(self.formatcommandstack(args))

  def savechangedmuddata(self, args):
    """
    save mud data that was changed
    """
    if args['trace']['changes']:
      self.changedmuddata.enqueue(args)
