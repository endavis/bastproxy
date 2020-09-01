"""
This module handles commands and parsing input

All commands are #bp.[package].[plugin].[command] or #bp.[plugin].[command]

Commands are stored in a dictionary, use #bp.commands.inspect -o data:commands to find what's in the dictionary
$cmd{'#bp.commands.inspect -o data:commands:stats -s'}
"""
import shlex
import os
import textwrap as _textwrap

from plugins._baseplugin import BasePlugin
from libs.persistentdict import PersistentDict
import libs.argp as argp

NAME = 'Commands'
SNAME = 'commands'
PURPOSE = 'Parse and handle commands'
AUTHOR = 'Bast'
VERSION = 1
PRIORITY = 10

# this plugin is required
REQUIRED = True

# this class creates a custom formatter for help text to wrap at 73 characters
# and it adds what the default value for an argument is if set
class CustomFormatter(argp.HelpFormatter):
  """
  custom formatter for argparser for commands
  """
  # override _fill_text
  def _fill_text(self, text, width, indent):
    """
    change the help text wrap at 73 characters

    arguments:
      required:
        text   - a string of items, newlines can be included
        width  - the width of the text to wrap, not used
        indent - the indent for each line after first, not used

    returns:
      returns a string of lines separated by newlines
    """
    text = _textwrap.dedent(text)
    lines = text.split('\n')
    multiline_text = ''
    for line in lines:
      wrapped_line = _textwrap.fill(line, 73)
      multiline_text = multiline_text + '\n' + wrapped_line
    return multiline_text

  # override _get_help_string
  def _get_help_string(self, action):
    """
    get the help string for an action, which maps to an argument for a command

    arguments:
      required:
        action  - the action to get the help for

    returns:
      returns a formatted help string
    """
    thelp = action.help
    # we add the default value to the argument help
    if '%(default)' not in action.help:
      if action.default is not argp.SUPPRESS:
        defaulting_nargs = [argp.OPTIONAL, argp.ZERO_OR_MORE]
        if action.option_strings or action.nargs in defaulting_nargs:
          if action.default != '':
            thelp += ' (default: %(default)s)'
    return thelp

class Plugin(BasePlugin):
  """
  a class to manage internal commands
  """
  def __init__(self, *args, **kwargs):
    """
    init the class
    """
    BasePlugin.__init__(self, *args, **kwargs)

    # a list of commands, such as "core.log.set" or "clients.ssub.list"
    self.commands_list = []

    # a list of commands that should not be run again if already in the queue
    self.no_multiple_commands = {}

    # load the history
    self.history_save_file = os.path.join(self.save_directory, 'history.txt')
    self.command_history_dict = PersistentDict(self.history_save_file, 'c')
    if 'history' not in self.command_history_dict:
      self.command_history_dict['history'] = []
    self.command_history_data = self.command_history_dict['history']

    # add apis
    self.api('api.add')('add', self.api_add_command)
    self.api('api.add')('change', self.api_change_command)
    #self.api('api.add')('default', self.api_setdefault)
    self.api('api.add')('removeplugin', self.api_remove_plugin)
    self.api('api.add')('list', self.api_list_commands)
    self.api('api.add')('run', self.api_run)
    self.api('api.add')('cmdhelp', self.api_command_help)
    self.api('api.add')('prefix', self.api_get_prefix)

    self.dependencies = ['core.events', 'core.log', 'core.errors', 'core.fuzzy']

  def initialize(self):
    """
    initialize the plugin
    """
    BasePlugin.initialize(self)

    # add a datatype
    self.api('log.adddtype')(self.short_name)
    #self.api('log.console')(self.short_name)

    # initialize settings
    self.api('setting.add')('cmdprefix', '#bp', str,
                            'the command preamble for the proxy')
    self.api('setting.add')('spamcount', 20, int,
                            'the # of times a command can ' \
                             'be run before an antispam command')
    self.api('setting.add')('antispamcommand', 'look', str,
                            'the antispam command to send')
    self.api('setting.add')('cmdcount', 0, int,
                            'the # of times the current command has been run',
                            readonly=True)
    self.api('setting.add')('lastcmd', '', str,
                            'the last command that was sent to the mud',
                            readonly=True)
    self.api('setting.add')('historysize', 50, int,
                            'the size of the history to keep')

    # add commands
    parser = argp.ArgumentParser(add_help=False,
                                 description='list commands in a plugin')
    parser.add_argument('plugin',
                        help='the plugin to see help for',
                        default='',
                        nargs='?')
    parser.add_argument('command',
                        help='the command in the plugin (can be left out)',
                        default='',
                        nargs='?')
    self.api('commands.add')('list',
                             self.command_list,
                             shelp='list commands',
                             parser=parser,
                             showinhistory=False)

    parser = argp.ArgumentParser(add_help=False,
                                 description='list the command history')
    parser.add_argument('-c',
                        "--clear",
                        help="clear the history",
                        action='store_true')
    self.api('commands.add')('history',
                             self.command_history,
                             shelp='list or run a command in history',
                             parser=parser,
                             showinhistory=False)

    parser = argp.ArgumentParser(add_help=False,
                                 description='run a command in history')
    parser.add_argument('number',
                        help='the history # to run',
                        default=-1,
                        nargs='?',
                        type=int)
    self.api('commands.add')('!',
                             self.command_runhistory,
                             shelp='run a command in history',
                             parser=parser,
                             preamble=False,
                             format=False,
                             showinhistory=False)

    # register events
    self.api('events.register')('io_execute_event', self.check_command, prio=5)
    self.api('events.register')('plugin_uninitialized', self._plugin_uninitialized)
    self.api('events.register')('plugin_%s_savestate' % self.short_name, self._savestate)

  def _plugin_uninitialized(self, args):
    """
    a plugin was uninitialized

    registered to the plugin_uninitialized event
    """
    self.api('send.msg')('removing commands for plugin %s' % args['plugin_id'],
                         secondary=args['short_name'])
    self.api('%s.removeplugin' % self.short_name)(args['short_name'])

  # remove all commands for a plugin
  def api_remove_plugin(self, plugin):
    """  remove all commands for a plugin
    @Yshort_name@w    = the plugin to remove commands for

    this function returns no values"""
    # get the plugin instance
    plugin_instance = self.api('core.plugins:get:plugin:instance')(plugin)

    if plugin_instance:
      # remove commands from command_list that start with plugin_instance.plugin_id
      new_commands = [command for command in self.commands_list if not command.startswith(plugin_instance.plugin_id)]
      self.commands_list = new_commands

  def format_return_msg(self, msg, short_name, command):
    """
    format a return message

    arguments:
      required:
        msg         - the message
        short_name  - the short name of the plugin
        command     - the command from the plugin

    returns:
      the updated message
    """
    line_length = self.api('setting.gets')('linelen', 'proxy')

    msg.insert(0, '')
    msg.insert(1, '%s.%s.%s' % (self.api('setting.gets')('cmdprefix'), short_name, command))
    msg.insert(2, '@G' + '-' * line_length + '@w')
    msg.append('@G' + '-' * line_length + '@w')
    msg.append('')
    return msg

  # return the command prefix setting
  def api_get_prefix(self):
    """
    return the current command prefix
    """
    return self.api('setting.gets')('commandprefix')

  # change an attribute for a command
  def api_change_command(self, plugin, command, flag, value):
    """
    change an attribute for a command

    arguments:
      required:
        plugin   - the plugin that the command is in
        command  - the command name
        flag     - the flag to set
        value    - the value of the flag

    returns:
      return True if successful, False if not
    """
    # get the command data for the plugin
    plugin_instance = self.api('core.plugins:get:plugin:instance')(plugin)
    command_data = self.get_command(plugin_instance.plugin_id, command_name)

    # didn't find the command
    if not command_data:
      self.api('send.error')('command %s does not exist in plugin %s' % \
        (command, plugin))
      return False

    # flag isn't in the command
    if flag not in command_data:
      self.api('send.error')(
          'flag %s does not exist in command %s in plugin %s' % \
            (flag, command, plugin))
      return False

    # change the flag and update the command data for the plugin
    data = self.api('data.get')('commands', plugin=plugin_instance.plugin_id)
    if not data:
      data = {}
    data[command][flag] = value

    self.api('data.update')('commands', data, plugin=plugin_instance.plugin_id)

    return True

  # return the help for a command
  def api_command_help(self, plugin, command):
    """
    get the help for a command

    arguments:
      required:
        plugin   - the plugin that the command is in
        command  - the command name

    returns:
      returns a the help message as a string
    """
    # get the command data for the plugin
    plugin_instance = self.api('core.plugins:get:plugin:instance')(plugin)
    command_data = self.get_command(plugin_instance.plugin_id, command_name)

    if command_data:
      return command_data['parser'].format_help()

    return ''

  # return a formatted list of commands for a plugin
  def api_list_commands(self, plugin, cformat=True):
    """
    list commands for a plugin

    arguments:
      required:
        plugin   - the plugin that the command is in
        cformat  -

    returns:
      returns a dictionary of commands
    """
    if cformat:
      return self.list_commands(plugin)
    else:
      plugin_instance = self.api('plugins.getp')(plugin)

      data = self.api('data.get')('commands', plugin=plugin_instance.plugin_id)
      return data

    return {}

  # run a command and return the output
  def api_run(self, plugin, command_name, argument_string):
    """
    run a command and return the output
    """
    command = self.get_command(plugin, command_name)

    if command:
      args, dummy = command['parser'].parse_known_args(argument_string)

      args = vars(args)

      if args['help']:
        return command['parser'].format_help().split('\n')

      return command['func'](args)

    return None

  def run_command(self, command, targs, full_arguments, data):
    """
    run a command that has an ArgParser
    """
    retval = False
    command_ran = '%s.%s.%s %s' % (self.api('setting.gets')('cmdprefix'),
                                   command['short_name'], command['commandname'], full_arguments)

    # add a trace if needed
    if 'trace' in data:
      data['trace']['changes'].append({'flag':'Start',
                                       'data':"'%s'" % command_ran,
                                       'plugin':self.short_name})

    # parse the arguments and deal with errors
    try:
      args, dummy = command['parser'].parse_known_args(targs)
    except argp.ArgumentError, exc:
      tmsg = []
      tmsg.append('Error: %s' % exc.errormsg) # pylint: disable=no-member
      tmsg.extend(command['parser'].format_help().split('\n'))
      self.api('send.client')('\n'.join(
          self.format_return_msg(tmsg,
                                 command['short_name'],
                                 command['commandname'])))
      if 'trace' in data:
        data['trace']['changes'].append(
            {'flag': 'Error',
             'data':'%s - error parsing args: %s' % (command_ran, exc.errormsg), # pylint: disable=no-member
             'plugin':self.short_name})
      return retval


    args = vars(args)
    args['fullargs'] = full_arguments

    # return help if flagged
    if args['help']:
      msg = command['parser'].format_help().split('\n')
      self.api('send.client')('\n'.join(
          self.format_return_msg(msg,
                                 command['short_name'],
                                 command['commandname'])))

    # deal with output and success from running the command
    else:
      args['data'] = data
      return_value = command['func'](args)
      if isinstance(return_value, tuple):
        retval = return_value[0]
        msg = return_value[1]
      else:
        retval = return_value
        msg = []

      # did not succeed
      if retval is False:
        msg.append('')
        msg.extend(command['parser'].format_help().split('\n'))
        self.api('send.client')('\n'.join(
            self.format_return_msg(msg,
                                   command['short_name'],
                                   command['commandname'])))

      # succeeded
      else:
        self.add_command_to_history(data, command)
        # if the format flag is not set then the data is returned
        if (not command['format']) and msg:
          self.api('send.client')(msg, preamble=command['preamble'])
        # if the format flag is set, then format the data to the client
        elif msg:
          self.api('send.client')('\n'.join(
              self.format_return_msg(msg,
                                     command['short_name'],
                                     command['commandname'])),
                                  preamble=command['preamble'])

    if 'trace' in data:
      data['trace']['changes'].append({'flag':'Finish',
                                       'data':"'%s'" % command_ran,
                                       'plugin':self.short_name})

    return retval

  def add_command_to_history(self, data, command=None):
    """
    add to the command history
    """
    # if showinhistory is false in either data or command, don't add
    if 'showinhistory' in data and not data['showinhistory']:
      return False
    if command and not command['showinhistory']:
      return False

    tdat = data['fromdata']
    if data['fromclient']:
      # remove existing
      if tdat in self.command_history_data:
        self.command_history_data.remove(tdat)

      # append the command
      self.command_history_data.append(tdat)

      # if the size is greater than historysize, pop the first item
      if len(self.command_history_data) >= self.api('setting.gets')('historysize'):
        self.command_history_data.pop(0)

      # sync command history
      self.command_history_dict.sync()
      return True

    return False

  # return a list of all commands known
  def api_get_all_commands_list(self):
    """
    return a list of all commands
    """
    return self.commands_list

  # retrieve a command from a plugin
  def get_command(self, plugin_id, command):
    """
    get the command from the plugin data
    """
    # find the instance
    plugin_instance = self.api('core.plugins:get:plugin:instance')(plugin_id)

    # retrieve the commands data
    data = self.api('data.get')('commands', plugin=plugin_instance.plugin_id)
    if not data:
      return None

    # return the command
    if command in data:
      return data[command]

    return None

  # update a command
  def update_command(self, plugin, command_name, data):
    """
    update a command
    """
    plugin_instance = self.api('core.plugins:get:plugin:instance')(plugin)

    all_command_data = self.api('data.get')('commands', plugin=plugin_instance.plugin_id)

    if not all_command_data:
      all_command_data = {}

    if command_name not in all_command_data:
      if not self.api.startup:
        self.api('send.msg')('commands - update_command: plugin %s does not have command %s' % \
                              (plugin, command_name),
                             secondary=plugin_instance.short_name)

    all_command_data[command_name] = data

    self.api('data.update')('commands', all_command_data, plugin=plugin_instance.plugin_id)

    return None

  def pass_through_command(self, data, command_data_dict):
    """
    pass through data to the proxy if it isn't a #bp command
    we add it to history and check antispam
    """
    # if it isn't a #bp command, we add it to history and do some checks
    # before sending it to the mud
    addedtohistory = self.add_command_to_history(data)

    # if the command is the same as the last command, do antispam checks
    if command_data_dict['orig'].strip() == self.api('setting.gets')('lastcmd'):
      self.api('setting.change')('cmdcount',
                                 self.api('setting.gets')('cmdcount') + 1)

      # if the command has been sent spamcount times, then we send an antispam
      # command in between
      if self.api('setting.gets')('cmdcount') == \
                            self.api('setting.gets')('spamcount'):
        data['fromdata'] = self.api('setting.gets')('antispamcommand') \
                                    + '|' + command_data_dict['orig']
        if 'trace' in data:
          data['addedtohistory'] = addedtohistory
          data['trace']['changes'].append(
              {'flag':'Antispam',
               'data':'command was sent %s times, sending %s for antispam' % \
                    (self.api('setting.gets')('spamcount'),
                     self.api('setting.gets')('antispamcommand')),
               'plugin':self.short_name})
        self.api('send.msg')('adding look for 20 commands')
        self.api('setting.change')('cmdcount', 0)
        return data

      # if the command is seen multiple times in a row and it has been flagged to only be sent once,
      # swallow it
      if command_data_dict['orig'] in self.no_multiple_commands:
        if 'trace' in data:
          data['trace']['changes'].append(
              {'flag':'Nomultiple',
               'data':'This command has been flagged" \
                  " not to be sent multiple times in a row',
               'plugin':self.short_name})

        data['fromdata'] = ''
        return data
    else:
      # the command does not match the last command
      self.api('setting.change')('cmdcount', 0)
      self.api('send.msg')('resetting command to %s' % command_data_dict['orig'].strip())
      self.api('setting.change')('lastcmd', command_data_dict['orig'].strip())

    # add a trace if it is unknow how the command was changed
    if data['fromdata'] != command_data_dict['orig']:
      if 'trace' in data:
        data['trace']['changes'].append(
            {'flag':'Unknown',
             'data':"'%s' - Don't know why we got here" % data['fromdata'],
             'plugin':self.short_name})

    return data

  def check_command(self, data):
    """
    check a line from a client for a command
    """
    command_data_dict = {}
    command_data_dict['orig'] = data['fromdata']
    command_data_dict['commandran'] = data['fromdata']
    command_data_dict['flag'] = 'Unknown'
    command_data_dict['cmd'] = None
    command_data_dict['data'] = data

    # if no data, skip this
    if command_data_dict['orig'] == '':
      return None

    commandprefix = self.api('setting.gets')('cmdprefix')
    # if it isn't a command, pass it through
    if command_data_dict['orig'][0:len(commandprefix)].lower() != commandprefix:
      return self.pass_through_command(data, command_data_dict)

    self.api('send.msg')('got command: %s' % command_data_dict['orig'])

    # split it with shlex
    try:
      split_args = shlex.split(command_data_dict['orig'].strip())
    except ValueError:
      self.api('send.traceback')('could not parse command')
      data['fromdata'] = ''
      return data

    # split out the full argument string
    try:
      first_space = command_data_dict['orig'].index(' ')
      full_args_string = command_data_dict['orig'][first_space+1:]
    except ValueError:
      full_args_string = ''

    # find which command we are
    command = split_args.pop(0)

    # split the command at .
    split_command_list = command.split('.')

    if len(split_command_list) > 4:
      command_data_dict['flag'] = 'Bad Command'
      command_data_dict['cmddata'] = 'Command name too long: %s' % command
    else:
      short_names = self.api('core.plugins:get:all:short:names')()
      loaded_plugin_ids = self.api('core.plugins:get:loaded:plugins:list')()

      plugin_package = None
      plugin_id = None
      plugin_command = None

      found_plugin = None
      found_package = None
      found_command = None

      # parse the command to get what to search for
      if len(split_command_list) == 1: # this would be cmdprefix by iself, ex. #bp
        # run #bp.commands.list
        pass
      elif len(split_command_list) == 2: # this would be cmdprefix + plugin_id, ex. #bp.ali
        plugin_id = split_command_list[1]
      elif len(split_command_list) == 3: # this would be cmdprefix + plugin_id + command, ex. #bp.alias.list
                                         # also could be cmdprefix + package + plugin_id
        # first check if the last part is a plugin
        found_plugin = self.api('fuzzy.get.best.match')(split_command_list[-1], short_names)
        if found_plugin:
          plugin_id = split_command_list[-1]
          plugin_package = split_command_list[1]
        # if not, then set plugin_id and plugin_command for later lookup
        else:
          plugin_id = split_command_list[1]
          plugin_command = split_command_list[-1]
      else: # len(split_command_list) == 4 would be cmdprefix + package + plugin_id + command, ex. #bp.client.alias.list
        plugin_package = split_command_list[1]
        plugin_id = split_command_list[2]
        plugin_command = split_command_list[-1]

      # print 'fullcommand: %s' % command
      # print 'plugin_package: %s' % plugin_package
      # print 'plugin: %s' % plugin_id
      # print 'command: %s' % plugin_command

      # find package
      if plugin_package and not found_package:
        packages = self.api('core.plugins:get:packages:list')()
        found_package = self.api('core.fuzzy:get:best:match')(plugin_package, packages)

      # find plugin
      if found_package and plugin_id and not found_plugin:
        plugin_list = [i.split('.')[-1] for i in loaded_plugin_ids if i.startswith('%s.' % found_package)]
        found_plugin = self.api('fuzzy.get.best.match')(plugin_id, plugin_list)
        if not found_plugin:
          new_plugin = self.api('fuzzy.get.best.match')(found_package + '.' + plugin_id, loaded_plugin_ids)
          if new_plugin:
            found_plugin = new_plugin.split('.')[-1]

      if not found_plugin and plugin_id:
        found_plugin = self.api('fuzzy.get.best.match')(plugin_id, short_names)

      # if a plugin was found but we don't have a package, find the package
      if found_plugin and plugin_id and not found_package:
        packages = []
        for plugin_id in loaded_plugin_ids:
          if found_plugin in plugin_id:
            packages.append(plugin_id.split('.')[0])
        if len(packages) == 1:
          found_package = packages[0]

      # didn't find anything
      if not found_plugin and not found_package and not found_command:
        command_data_dict['cmd'] = self.get_command(self.short_name, 'list')
        command_data_dict['commandran'] = '%s.%s.%s' % \
              (self.api('setting.gets')('cmdprefix'),
               self.short_name,
               'list')
        command_data_dict['flag'] = 'List2'
        command_data_dict['targs'] = []
        command_data_dict['fullargs'] = ''

      # couldn't find a plugin
      elif not found_plugin:

        command_data_dict['flag'] = 'Bad Command'
        command_data_dict['cmddata'] = 'could not find command %s' % command

      # at least have a plugin
      else:
        if plugin_command:
          commands = self.api('core.commands:get:plugin:command:data')(found_plugin).keys()
          found_command = self.api('core.fuzzy:get:best:match')(plugin_command, commands)

        # have a plugin but no command
        if found_plugin and not found_command:

          if plugin_command:
            command_data_dict['flag'] = 'Bad Command'
            command_data_dict['cmddata'] = 'command %s does not exist in plugin %s' % (plugin_command, found_plugin)
          else:
            command_data_dict['cmd'] = self.get_command(self.short_name, 'list')
            command_data_dict['flag'] = 'Help'
            command_data_dict['commandran'] = '%s.%s.%s %s' % \
                    (self.api('setting.gets')('cmdprefix'),
                     self.short_name, 'list', found_plugin)
            command_data_dict['targs'] = [found_plugin]
            command_data_dict['fullargs'] = full_args_string

        # have a plugin and a command
        else:
          command = self.get_command(found_plugin, found_command)
          command_data_dict['cmd'] = command
          command_data_dict['commandran'] = '%s.%s.%s %s' % \
                (self.api('setting.gets')('cmdprefix'), found_plugin,
                 command['commandname'], ' '.join(split_args))
          command_data_dict['flag'] = 'Run'
          command_data_dict['targs'] = split_args
          command_data_dict['fullargs'] = full_args_string

      # print 'fullcommand: %s' % command
      # print 'found_package: %s' % found_package
      # print 'found_plugin: %s' % found_plugin
      # print 'found_command: %s' % found_command

      command_data_dict['short_name'] = found_plugin
      command_data_dict['scmd'] = found_command

      # run the command here
      if command_data_dict['flag'] == 'Bad Command':
        self.api('send.client')("@R%s@W is not a command" % (command))
      else:
        try:
          command_data_dict['success'] = self.run_command(command_data_dict['cmd'],
                                                          command_data_dict['targs'],
                                                          command_data_dict['fullargs'],
                                                          command_data_dict['data'])
        except Exception:  # pylint: disable=broad-except
          command_data_dict['success'] = 'Error'
          self.api('send.traceback')(
              'Error when calling command %s.%s' % (command_data_dict['short_name'],
                                                    command_data_dict['scmd']))
        command_data_dict['cmddata'] = "'%s' - %s" % (command_data_dict['commandran'],
                                                      'Outcome: %s' % command_data_dict['success'])

      if 'trace' in data:
        data['trace']['changes'].append({'flag': command_data_dict['flag'],
                                         'data':command_data_dict['cmddata'],
                                         'plugin':self.short_name})
      return {'fromdata':''}

  # add a command
  def api_add_command(self, command_name, func, **kwargs):
    # pylint: disable=too-many-branches
    """  add a command
    @Ycommand_name@w  = the base that the api should be under
    @Yfunc@w   = the function that should be run when this command is executed
    @Ykeyword arguments@w
      @Yshelp@w    = the short help, a brief description of what the
                                          command does
      @Ylhelp@w    = a longer description of what the command does
      @Ypreamble@w = show the preamble for this command (default: True)
      @Yformat@w   = format this command (default: True)
      @Ygroup@w    = the group this command is in
      @Yparser@w   = the parser for the argument

    The command will be added as short_name.command_name

    short_name is gotten from the class the function belongs to or the short_name key
      in args

    this function returns no values"""

    args = kwargs.copy()

    called_from = self.api('api.callerplugin')()

    long_name = None

    # passed an empty function
    if not func:
      self.api('send.error')(
          'add command for command %s was passed a null function from plugin %s, not adding' % \
                (command_name, called_from), secondary=called_from)
      return

    # find the plugin_id and short_name
    try:
      short_name = func.im_self.short_name
      plugin_id = func.im_self.plugin_id
    except AttributeError:
      try:
        plugin = func.im_self.plugin
        short_name = plugin.short_name
        plugin_id = plugin.plugin_id
      except AttributeError:
        if 'short_name' in args:
          short_name = args['short_name']
        else:
          call_stack = self.api('api.callstack')()
          self.api('send.error')(
              'Function is not part of a plugin class: command %s from plugin %s' % \
                    (command_name, called_from), secondary=called_from)
          self.api('send.error')("\n".join(call_stack).strip())
          return

    # add custom formatter to the parser passed in
    if 'parser' in args:
      new_parser = args['parser']
      new_parser.formatter_class = CustomFormatter

    # use default parser if none passed in
    else:
      self.api('send.msg')('adding default parser to command %s.%s' % \
                                      (short_name, command_name))
      if 'shelp' not in args:
        args['shelp'] = 'there is no help for this command'
      new_parser = argp.ArgumentParser(add_help=False,
                                       description=args['shelp'])
      args['parser'] = new_parser

    try:
      new_parser.add_argument("-h", "--help", help="show help",
                              action="store_true")
    except argp.ArgumentError:
      pass

    new_parser.prog = '@B%s.%s.%s@w' % (self.api('setting.gets')('cmdprefix'),
                                        short_name, command_name)

    # if no group, add the group as the plugin_name
    if 'group' not in args:
      args['group'] = short_name

    try:
      long_name = func.im_self.name
      args['lname'] = long_name
    except AttributeError:
      pass

    if 'lname' not in args:
      self.api('send.msg')('command %s.%s has no long name, not adding' % \
                                            (short_name, command_name),
                           secondary=short_name)
      return

    # build the command dict
    args['func'] = func
    args['short_name'] = short_name
    args['lname'] = long_name
    args['commandname'] = command_name
    if 'preamble' not in args:
      args['preamble'] = True
    if 'format' not in args:
      args['format'] = True
    if 'showinhistory' not in args:
      args['showinhistory'] = True

    # update the command
    plugin_instance = self.api('core.plugins:get:plugin:instance')(plugin_id)
    self.update_command(plugin_instance.plugin_id, command_name, args)

    self.commands_list.append('%s.%s' % (plugin_instance.plugin_id, command_name))

    self.api('send.msg')('added command %s.%s' % \
                                            (short_name, command_name),
                         secondary=short_name)

  # remove a command
  def api_remove_command(self, plugin, command_name):
    """  remove a command
    @Yshort_name@w    = the top level of the command
    @Ycommand_name@w  = the name of the command

    this function returns no values"""
    plugin_instance = self.api('core.plugins:get:plugin:instance')(plugin)
    removed = False
    if plugin_instance:
      data = self.api('data.get')('commands', plugin=plugin_instance.plugin_id)
      if data and command_name in data:
        del data[command_name]
        self.api('data.update')('commands', data, plugin=plugin_instance.plugin_id)
        self.api('send.msg')('removed command %s.%s' % \
                                                (plugin, command_name),
                             secondary=plugin)
        removed = True

    if not removed:
      self.api('send.msg')('remove command: command %s.%s does not exist' % \
                                                (plugin, command_name),
                           secondary=plugin)

  def format_command_list(self, command_list):
    """
    format a list of commands by a category
    """
    tmsg = []
    for i in command_list:
      if i != 'default':
        tlist = i['parser'].description.split('\n')
        if not tlist[0]:
          tlist.pop(0)
        tmsg.append('  @B%-10s@w : %s' % (i['commandname'], tlist[0]))

    return tmsg

  def list_commands(self, plugin):
    """
    build a table of commands for a category
    """
    plugin_instance = self.api('core.plugins:get:plugin:instance')(plugin)

    tmsg = []
    if plugin_instance:
      commands = self.api('data.get')('commands', plugin=plugin_instance.plugin_id)
      tmsg.append('Commands in %s:' % plugin_instance.plugin_id)
      tmsg.append('@G' + '-' * 60 + '@w')
      groups = {}
      for i in sorted(commands.keys()):
        if i != 'default':
          if commands[i]['group'] not in groups:
            groups[commands[i]['group']] = []

          groups[commands[i]['group']].append(commands[i])

      for group in sorted(groups.keys()):
        if group != 'Base':
          tmsg.append('@M' + '-' * 5 + ' ' +  group + ' ' + '-' * 5)
          tmsg.extend(self.format_command_list(groups[group]))
          tmsg.append('')

      tmsg.append('@M' + '-' * 5 + ' ' +  'Base' + ' ' + '-' * 5)
      tmsg.extend(self.format_command_list(groups['Base']))
      #tmsg.append('@G' + '-' * 60 + '@w')
    return tmsg

  def command_list(self, args):
    """
    list commands
    """
    tmsg = []
    plugin_instance = self.api('core.plugins:get:plugin:instance')(args['plugin'])
    command = args['command']
    if plugin_instance:
      plugin_commands = self.api('data:get')('commands', plugin_instance.plugin_id)
      if plugin_commands:
        if command and command in plugin_commands:
          msg = plugin_commands[command]['parser'].format_help().split('\n')
          tmsg.extend(msg)
        else:
          tmsg.extend(self.list_commands(plugin_instance.short_name))
      else:
        tmsg.append('There are no commands in plugin %s' % plugin_instance.short_name)
    else:
      tmsg.append('Plugins')
      short_name_list = self.api('core.plugins:get:all:short:names')()
      short_name_list.sort()
      tmsg.append(self.api('utils.listtocolumns')(short_name_list, cols=3, columnwise=False, gap=6))
    return True, tmsg

  def command_runhistory(self, args):
    """
    act on the command history
    """
    if len(self.command_history_data) < abs(args['number']):
      return True, ['# is outside of history length']

    if len(self.command_history_data) >= self.api('setting.gets')('historysize'):
      command = self.command_history_data[args['number'] - 1]
    else:
      command = self.command_history_data[args['number']]

    self.api('send.client')('history: sending "%s"' % command)
    self.api('send.execute')(command)

    return True, []

  def command_history(self, args):
    """
    act on the command history
    """
    tmsg = []

    if args['clear']:
      del self.command_history_dict['history'][:]
      self.command_history_dict.sync()
      tmsg.append('Command history cleared')
    else:
      for i in self.command_history_data:
        tmsg.append('%s : %s' % (self.command_history_data.index(i), i))

    return True, tmsg

  def _savestate(self, _=None):
    """
    save states
    """
    self.command_history_dict.sync()
