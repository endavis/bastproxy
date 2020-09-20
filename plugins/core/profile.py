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

    self.command_traces = None
    self.changed_mud_data = None

  def initialize(self):
    """
    initialize the plugin
    """
    BasePlugin.initialize(self)

    self.api('setting:add')('commands', False, bool,
                            'flag to echo commands')
    self.api('setting:add')('functions', False, bool,
                            'flag to profile functions')
    self.api('setting:add')('stacklen', 20, int,
                            '# of traces kept')
    self.api('setting:add')('cmdfuncstack', False, bool,
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
    self.api('core.commands:command:add')('commands', self.cmd_commands,
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
    self.api('core.commands:command:add')('muddata', self.cmd_muddata,
                                          parser=parser)

    parser = argp.ArgumentParser(add_help=False,
                                 description='reset command stack')
    self.api('core.commands:command:add')('rstack', self.cmd_rstack,
                                          parser=parser)

    self.command_traces = SimpleQueue(self.api('setting:get')('stacklen'))
    self.changed_mud_data = SimpleQueue(self.api('setting:get')('stacklen'))

    self.api('core.events:register:to:event')('io_execute_trace_finished', self.savecommand, prio=99)
    self.api('core.events:register:to:event')('from_mud_event', self.savechanged_mud_data, prio=99)
    self.api('core.events:register:to:event')('%s_var_functions_modified' % self.plugin_id, self.onfunctionschange)

  def onfunctionschange(self, _=None):
    """
    toggle the function profiling
    """
    functions = self.api('setting:get')('functions')
    self.api('libs.timing:timing:toggle')(functions)

  def listcommands(self):
    """
    list the command profiles that have been saved
    """
    message = ['Command Traces:']
    for i in self.command_traces.items:
      message.append('  %s' % i['originalcommand'])
    return True, message

  def listchanged_mud_data(self):
    """
    list the muddata profiles that have been saved
    """
    self.changed_mud_data.takesnapshot()
    items = self.changed_mud_data.getsnapshot()
    message = ['Data Traces:']

    for i in range(0, len(items)):
      message.append('%-3s : %s' % (i, items[i]['trace']['original']))
    return True, message

  def showchanged_mud_data(self, item, callstack=False): # pylint: disable=unused-argument
    """
    find the changed muddata and print it
    """
    snapshot = self.changed_mud_data.getsnapshot()
    if not snapshot:
      self.changed_mud_data.takesnapshot()
      snapshot = self.changed_mud_data.getsnapshot()

    try:
      temp_item = snapshot[item]
      return True, [self.formatmuddatastack(temp_item)]
    except IndexError:
      return False, ['Could not find item: %s' % item]

  def showcommand(self, item, callstack=False):
    """
    find the command trace and format it
    """
    for i in self.command_traces.items:
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
      return self.showchanged_mud_data(int(args['item']), callstack=False)

    return self.listchanged_mud_data()

  def cmd_rstack(self, _=None):
    """
    reset the command trace
    """
    io_manager = self.api('managers:get')('io')

    message = []
    message.append('The following stack was active')
    message.append('%s' % io_manager.currenttrace)
    io_manager.currenttrace = None
    message.append('The stack has been reset')

    return True, message

  def formatmuddatastack(self, stack):
    """
    format the command stack
    """
    message = ['------------------- Muddata Trace -------------------']
    message.append('%-17s : %s' % ('Original', stack['trace']['original']))

    message.append('-------------- Internal Stack --------------')
    count = 0
    for i in stack['trace']['changes']:
      count = count + 1
      if 'plugin' in i and i['plugin']:
        apicall = '%s.formatmuddatatraceitem' % i['plugin']
        if self.api('api.has')(apicall):
          message.append(self.api(apicall)(i))
          continue

      message.append("%-2s - %-15s :   %s - %s" % (count, i['plugin'].capitalize(), i['flag'],
                                                   i['data']))

    return '\n'.join(message)

  def formatcommandstack(self, stack, callstack=False):
    """
    format the command stack
    """
    message = ['------------------- Command Trace -------------------']
    message.append('%-17s : %s' % ('Original', stack['originalcommand']))
    if stack['fromclient']:
      message.append('%-17s : from client' % 'Originated')
    if stack['internal']:
      message.append('%-17s : Internal' % 'Originated')
    if 'fromplugin' in stack and stack['fromplugin']:
      message.append('%-17s : %s' % ('Plugin', stack['fromplugin']))
    message.append('%-17s : %s' % ('Show in History', stack['showinhistory']))
    message.append('%-17s : %s' % ('Added to History', stack['addedtohistory']))

    message.append('-------------- Internal Stack --------------')
    count = 0
    for i in stack['changes']:
      count = count + 1
      if 'plugin' in i and i['plugin']:
        apicall = '%s.formatcmdtraceitem' % i['plugin']
        if self.api('api.has')(apicall):
          message.append(self.api(apicall)(i))
          continue

      message.append("%-2s - %-15s :   %s - %s" % (count, i['plugin'].capitalize(), i['flag'],
                                                   i['data']))

      if callstack and 'callstack' in i:
        for line in i['callstack']:
          message.append("%-20s :   %s" % ("", line))

    message.append('-----------------------------------------------------')


    return '\n'.join(message)

  def savecommand(self, args):
    """
    echo the command
    """
    self.command_traces.enqueue(args)

    echocommands = self.api('setting:get')('commands')

    if echocommands:
      self.api('send:client')(self.formatcommandstack(args))

  def savechanged_mud_data(self, args):
    """
    save mud data that was changed
    """
    if args['trace']['changes']:
      self.changed_mud_data.enqueue(args)
