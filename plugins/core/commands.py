"""
This module handles commands and parsing input

All commands are #bp.[plugin].[cmd]
"""
import sys
import shlex
import os
import textwrap as _textwrap
try:
  from fuzzywuzzy import process
except ImportError:
  print "Please install the fuzzywuzzy library: pip install fuzzywuzzy python-Levenshtein"
  sys.exit(1)

from plugins._baseplugin import BasePlugin
from libs.persistentdict import PersistentDict
import libs.argp as argp

NAME = 'Commands'
SNAME = 'commands'
PURPOSE = 'Parse and handle commands'
AUTHOR = 'Bast'
VERSION = 1
PRIORITY = 10

REQUIRED = True

class CustomFormatter(argp.HelpFormatter):
  """
  custom formatter for argparser for commands
  """
  def _fill_text(self, text, width, indent):
    """
    change the help text wrap at 73 characters
    """
    text = _textwrap.dedent(text)
    lines = text.split('\n')
    multiline_text = ''
    for line in lines:
      wrline = _textwrap.fill(line, 73)
      multiline_text = multiline_text + '\n' + wrline
    return multiline_text

  def _get_help_string(self, action):
    """
    get the help string for a command
    """
    thelp = action.help
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

    self.can_reload_f = False

    self.cmds = {}
    self.nomultiplecmds = {}

    self.savehistfile = os.path.join(self.save_directory, 'history.txt')
    self.cmdhistorydict = PersistentDict(self.savehistfile, 'c')
    if 'history' not in self.cmdhistorydict:
      self.cmdhistorydict['history'] = []
    self.cmdhistory = self.cmdhistorydict['history']

    self.api('api.add')('add', self.api_addcmd)
    self.api('api.add')('remove', self.api_removecmd)
    self.api('api.add')('change', self.api_changecmd)
    self.api('api.add')('default', self.api_setdefault)
    self.api('api.add')('removeplugin', self.api_removeplugin)
    self.api('api.add')('list', self.api_listcmds)
    self.api('api.add')('run', self.api_run)
    self.api('api.add')('cmdhelp', self.api_cmdhelp)
    self.api('api.add')('prefix', self._api_get_prefix)

    self.dependencies = ['core.events', 'core.log', 'core.errors']

  def initialize(self):
    """
    initialize the plugin
    """
    BasePlugin.initialize(self)
    self.api('log.adddtype')(self.short_name)
    #self.api('log.console')(self.short_name)

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

    parser = argp.ArgumentParser(add_help=False,
                                 description='list commands in a category')
    parser.add_argument('category',
                        help='the category to see help for',
                        default='',
                        nargs='?')
    parser.add_argument('cmd',
                        help='the command in the category (can be left out)',
                        default='',
                        nargs='?')
    self.api('commands.add')('list',
                             self.cmd_list,
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
                             self.cmd_history,
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
                             self.cmd_runhistory,
                             shelp='run a command in history',
                             parser=parser,
                             preamble=False,
                             format=False,
                             showinhistory=False)

    self.api('events.register')('io_execute_event', self.chkcmd_new, prio=5)
    self.api('events.register')('plugin_uninitialized', self.pluginuninitialized)
    self.api('events.eraise')('plugin_cmdman_loaded', {})

    self.api('events.register')('plugin_%s_savestate' % self.short_name, self._savestate)

  def pluginuninitialized(self, args):
    """
    a plugin was uninitialized
    """
    self.api('send.msg')('removing commands for plugin %s' % args['name'],
                         secondary=args['name'])
    self.api('%s.removeplugin' % self.short_name)(args['name'])

  def formatretmsg(self, msg, short_name, cmd):
    """
    format a return message
    """

    linelen = self.api('plugins.getp')('proxy').api('setting.gets')('linelen')

    msg.insert(0, '')
    msg.insert(1, '%s.%s.%s' % (self.api('setting.gets')('cmdprefix'), short_name, cmd))
    msg.insert(2, '@G' + '-' * linelen + '@w')
    msg.append('@G' + '-' * linelen + '@w')
    msg.append('')
    return msg

  def _api_get_prefix(self):
    """
    return the current command prefix
    """
    return self.api('setting.gets')('cmdprefix')

  # change an attribute for a command
  def api_changecmd(self, plugin, command, flag, value):
    """
    change an attribute for a command
    """
    if command not in self.cmds[plugin]:
      self.api('send.error')('command %s does not exist in plugin %s' % \
        (command, plugin))
      return False

    if flag not in self.cmds[plugin][command]:
      self.api('send.error')(
          'flag %s does not exist in command %s in plugin %s' % \
            (flag, command, plugin))
      return False

    self.cmds[plugin][command][flag] = value

    return True

  # return the help for a command
  def api_cmdhelp(self, plugin, cmd):
    """
    get the help for a command
    """
    if plugin in self.cmds and cmd in self.cmds[plugin]:
      return self.cmds[plugin][cmd]['parser'].format_help()

    return ''

  # return a formatted list of commands for a plugin
  def api_listcmds(self, plugin, cformat=True):
    """
    list commands for a plugin
    """
    if cformat:
      return self.listcmds(plugin)
    else:
      if plugin in self.cmds:
        return self.cmds[plugin]

      return {}

  # run a command and return the output
  def api_run(self, plugin, cmdname, argstring):
    """
    run a command and return the output
    """
    if plugin in self.cmds and cmdname in self.cmds[plugin]:
      cmd = self.cmds[plugin][cmdname]
      args, dummy = cmd['parser'].parse_known_args(argstring)

      args = vars(args)

      if args['help']:
        return cmd['parser'].format_help().split('\n')

      return cmd['func'](args)

    return None

  def runcmd(self, cmd, targs, fullargs, data):
    """
    run a command that has an ArgParser
    """
    retval = False
    commandran = '%s.%s.%s %s' % (self.api('setting.gets')('cmdprefix'),
                                  cmd['short_name'], cmd['commandname'], fullargs)

    if 'trace' in data:
      data['trace']['changes'].append({'flag':'Start',
                                       'data':"'%s'" % commandran,
                                       'plugin':self.short_name})

    try:
      args, dummy = cmd['parser'].parse_known_args(targs)
    except argp.ArgumentError, exc:
      tmsg = []
      tmsg.append('Error: %s' % exc.errormsg) # pylint: disable=no-member
      tmsg.extend(cmd['parser'].format_help().split('\n'))
      self.api('send.client')('\n'.join(
          self.formatretmsg(tmsg,
                            cmd['short_name'],
                            cmd['commandname'])))
      if 'trace' in data:
        data['trace']['changes'].append(
            {'flag': 'Error',
             'data':'%s - error parsing args: %s' % (commandran, exc.errormsg), # pylint: disable=no-member
             'plugin':self.short_name})
      return retval

    args = vars(args)
    args['fullargs'] = fullargs
    if args['help']:
      msg = cmd['parser'].format_help().split('\n')
      self.api('send.client')('\n'.join(
          self.formatretmsg(msg,
                            cmd['short_name'],
                            cmd['commandname'])))

    else:
      args['data'] = data
      retvalue = cmd['func'](args)
      if isinstance(retvalue, tuple):
        retval = retvalue[0]
        msg = retvalue[1]
      else:
        retval = retvalue
        msg = []

      if retval is False:
        msg.append('')
        msg.extend(cmd['parser'].format_help().split('\n'))
        self.api('send.client')('\n'.join(
            self.formatretmsg(msg,
                              cmd['short_name'],
                              cmd['commandname'])))
      else:
        self.addtohistory(data, cmd)
        if (not cmd['format']) and msg:
          self.api('send.client')(msg, preamble=cmd['preamble'])
        elif msg:
          self.api('send.client')('\n'.join(
              self.formatretmsg(msg,
                                cmd['short_name'],
                                cmd['commandname'])),
                                  preamble=cmd['preamble'])

    if 'trace' in data:
      data['trace']['changes'].append({'flag':'Finish',
                                       'data':"'%s'" % commandran,
                                       'plugin':self.short_name})

    return retval

  def addtohistory(self, data, cmd=None):
    """
    add to the command history
    """
    if 'showinhistory' in data and not data['showinhistory']:
      return False
    if cmd and not cmd['showinhistory']:
      return False

    tdat = data['fromdata']
    if data['fromclient']:
      if tdat in self.cmdhistory:
        self.cmdhistory.remove(tdat)
      self.cmdhistory.append(tdat)
      if len(self.cmdhistory) >= self.api('setting.gets')('historysize'):
        self.cmdhistory.pop(0)
      self.cmdhistorydict.sync()
      return True

    return False

  def sort_fuzzy_result(self, result):
    """
    sort a result from extract
    """
    newdict = {}
    for i in result:
      if not i[1] in newdict:
        newdict[i[1]] = []
      newdict[i[1]].append(i[0])
    return newdict

  def get_best_match(self, item_to_match, list_to_match):
    """
    get the best match of item in a list
    """
    found = None
    print 'get_best_match: item_to_match: %s' % item_to_match
    matching_startswith = [i for i in list_to_match if i.startswith(item_to_match)]
    if len(matching_startswith) == 1:
      found = matching_startswith[0]
      print 'get_best_match (startswith) matched %s to %s' % (item_to_match, found)
    else:
      sorted_extract = self.sort_fuzzy_result(process.extract(item_to_match, list_to_match))
      print 'extract for %s - %s' % (item_to_match, sorted_extract)
      maxscore = max(sorted_extract.keys())
      if maxscore > 80 and len(sorted_extract[maxscore]) == 1:
        found = sorted_extract[maxscore][0]
        print 'get_best_match (score) matched %s to %s' % (item_to_match, found)

    return found

  def api_get_all_commands_list(self):
    """
    return a list of all commands
    """
    cmdlist = []
    for sname in self.cmds:
      for command in self.cmds[sname]:
        cmdlist.append('%s.%s' % (sname, command))

    return self.cmds.keys(), cmdlist

  def pass_through_command(self, data, command_data_dict):
    """
    pass through data to the proxy if it isn't a #bp command
    we add it to history and check antispam
    """
    # if it isn't a #bp command, we add it to history and do some checks
    # before sending it to the mud
    addedtohistory = self.addtohistory(data)

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
               'data':'cmd was sent %s times, sending %s for antispam' % \
                    (self.api('setting.gets')('spamcount'),
                     self.api('setting.gets')('antispamcommand')),
               'plugin':self.short_name})
        self.api('send.msg')('adding look for 20 commands')
        self.api('setting.change')('cmdcount', 0)
        return data

      # if the command is seen multiple times in a row and it has been flagged to only be sent once,
      # swallow it
      if command_data_dict['orig'] in self.nomultiplecmds:
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

  def chkcmd_new(self, data):
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

    cmdprefix = self.api('setting.gets')('cmdprefix')
    # if it isn't a command, pass it through
    if command_data_dict['orig'][0:len(cmdprefix)].lower() != cmdprefix:
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
    cmd = split_args.pop(0)

    split_command_list = cmd.split('.')

    if len(split_command_list) > 4:
      command_data_dict['flag'] = 'Bad Command'
      command_data_dict['cmddata'] = 'Command name too long: %s' % cmd
    else:
      short_names, _ = self.api_get_all_commands_list()
      loaded_plugin_ids = self.api('plugins.loadedpluginslist')()

      package = None
      plugin_id = None
      plugin_cmd = None

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
        found_plugin = self.get_best_match(split_command_list[-1], short_names)
        if found_plugin:
          plugin_id = split_command_list[-1]
          found_package = split_command_list[1]
        # if not, then cmd to
        else:
          plugin_id = split_command_list[1]
          plugin_cmd = split_command_list[-1]
      else: # len(split_command_list) == 4 would be cmdprefix + package + plugin_id + command, ex. #bp.client.alias.list
        package = split_command_list[1]
        plugin_id = split_command_list[2]
        plugin_cmd = split_command_list[-1]

      print 'fullcommand: %s' % cmd
      print 'package: %s' % package
      print 'plugin: %s' % plugin_id
      print 'cmd: %s' % plugin_cmd

      # find package
      if package and not found_package:
        packages = self.api('plugins.packageslist')()
        found_package = self.get_best_match(package, packages)

      # find plugin
      if found_package and plugin_id and not found_plugin:
        plugin_list = [i.split('.')[-1] for i in loaded_plugin_ids if i.startswith('%s.' % found_package)]
        found_plugin = self.get_best_match(plugin_id, plugin_list)
        if not found_plugin:
          new_plugin = self.get_best_match(found_package + '.' + plugin_id, loaded_plugin_ids)
          if new_plugin:
            found_plugin = new_plugin.split('.')[-1]

      if not found_plugin and plugin_id:
        found_plugin = self.get_best_match(plugin_id, short_names)

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
        command_data_dict['cmd'] = self.cmds[self.short_name]['list']
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
        command_data_dict['cmddata'] = 'could not find command %s' % cmd

      # at least have a plugin
      else:
        if plugin_cmd:
          cmds = self.api('commands.list')(found_plugin, cformat=False).keys()
          found_command = self.get_best_match(plugin_cmd, cmds)

        # have a plugin but no command
        if found_plugin and not found_command:

          if plugin_cmd:
            command_data_dict['flag'] = 'Bad Command'
            command_data_dict['cmddata'] = 'command %s does not exist in plugin %s' % (plugin_cmd, found_plugin)
          else:
            command_data_dict['cmd'] = self.cmds[self.short_name]['list']
            command_data_dict['flag'] = 'Help'
            command_data_dict['commandran'] = '%s.%s.%s %s' % \
                    (self.api('setting.gets')('cmdprefix'),
                     self.short_name, 'list', found_plugin)
            command_data_dict['targs'] = [found_plugin]
            command_data_dict['fullargs'] = full_args_string

        # have a plugin and a command
        else:
          cmd = self.cmds[found_plugin][found_command]
          command_data_dict['cmd'] = cmd
          command_data_dict['commandran'] = '%s.%s.%s %s' % \
                (self.api('setting.gets')('cmdprefix'), found_plugin,
                 cmd['commandname'], ' '.join(split_args))
          command_data_dict['flag'] = 'Run'
          command_data_dict['targs'] = split_args
          command_data_dict['fullargs'] = full_args_string

      print 'fullcommand: %s' % cmd
      print 'found_package: %s' % found_package
      print 'found_plugin: %s' % found_plugin
      print 'found_command: %s' % found_command

      command_data_dict['short_name'] = found_plugin
      command_data_dict['scmd'] = found_command

      # run the command here
      if command_data_dict['flag'] == 'Bad Command':
        self.api('send.client')("@R%s.%s@W is not a command" % \
              (command_data_dict['short_name'], command_data_dict['scmd']))
      else:
        try:
          command_data_dict['success'] = self.runcmd(command_data_dict['cmd'],
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
  def api_addcmd(self, cmdname, func, **kwargs):
    # pylint: disable=too-many-branches
    """  add a command
    @Ycmdname@w  = the base that the api should be under
    @Yfunc@w   = the function that should be run when this command is executed
    @Ykeyword arguments@w
      @Yshelp@w    = the short help, a brief description of what the
                                          command does
      @Ylhelp@w    = a longer description of what the command does
      @Ypreamble@w = show the preamble for this command (default: True)
      @Yformat@w   = format this command (default: True)
      @Ygroup@w    = the group this command is in

    The command will be added as short_name.cmdname

    short_name is gotten from the class the function belongs to or the short_name key
      in args

    this function returns no values"""

    args = kwargs.copy()

    calledfrom = self.api('api.callerplugin')()

    lname = None
    if not func:
      self.api('send.error')(
          'add cmd for cmd %s was passed a null function from plugin %s, not adding' % \
                (cmdname, calledfrom), secondary=calledfrom)
      return
    try:
      short_name = func.im_self.short_name
    except AttributeError:
      if 'short_name' in args:
        short_name = args['short_name']
      else:
        callstack = self.api('api.callstack')()
        self.api('send.error')(
            'Function is not part of a plugin class: cmd %s from plugin %s' % \
                  (cmdname, calledfrom), secondary=calledfrom)
        self.api('send.error')("\n".join(callstack).strip())
        return

    if 'parser' in args:
      tparser = args['parser']
      tparser.formatter_class = CustomFormatter

    else:
      self.api('send.msg')('adding default parser to command %s.%s' % \
                                      (short_name, cmdname))
      if 'shelp' not in args:
        args['shelp'] = 'there is no help for this command'
      tparser = argp.ArgumentParser(add_help=False,
                                    description=args['shelp'])
      args['parser'] = tparser

    tparser.add_argument("-h", "--help", help="show help",
                         action="store_true")

    tparser.prog = '@B%s.%s.%s@w' % (self.api('setting.gets')('cmdprefix'),
                                     short_name, cmdname)

    if 'group' not in args:
      args['group'] = short_name


    try:
      lname = func.im_self.name
      args['lname'] = lname
    except AttributeError:
      pass

    if 'lname' not in args:
      self.api('send.msg')('cmd %s.%s has no long name, not adding' % \
                                            (short_name, cmdname),
                           secondary=short_name)
      return

    self.api('send.msg')('added cmd %s.%s' % \
                                            (short_name, cmdname),
                         secondary=short_name)

    if short_name not in self.cmds:
      self.cmds[short_name] = {}
    args['func'] = func
    args['short_name'] = short_name
    args['lname'] = lname
    args['commandname'] = cmdname
    if 'preamble' not in args:
      args['preamble'] = True
    if 'format' not in args:
      args['format'] = True
    if 'showinhistory' not in args:
      args['showinhistory'] = True
    self.cmds[short_name][cmdname] = args

  # remove a command
  def api_removecmd(self, plugin, cmdname):
    """  remove a command
    @Yshort_name@w    = the top level of the command
    @Ycmdname@w  = the name of the command

    this function returns no values"""
    if plugin in self.cmds and cmdname in self.cmds[plugin]:
      del self.cmds[plugin][cmdname]
    else:
      self.api('send.msg')('remove cmd: cmd %s.%s does not exist' % \
                                                (plugin, cmdname),
                           secondary=plugin)

    self.api('send.msg')('removed cmd %s.%s' % \
                                                (plugin, cmdname),
                         secondary=plugin)

  # set the default command for a plugin
  def api_setdefault(self, cmd, plugin=None):
    """  set the default command for a plugin
    @Yshort_name@w    = the plugin of the command
    @Ycmdname@w  = the name of the command

    this function returns True if the command exists, False if it doesn't"""

    if not plugin:
      plugin = self.api('api.callerplugin')(ignore_plugin_list=[self.short_name])

    if not plugin:
      self.api('send.error')('could not add a default cmd: %s' % cmd)
      return False

    if plugin in self.cmds and cmd in self.cmds[plugin]:
      self.api('send.msg')('added default command %s for plugin %s' % (cmd, plugin),
                           secondary=plugin)
      self.cmds[plugin]['default'] = self.cmds[plugin][cmd]
      return True

    self.api('send.error')('could not set default command %s for plugin %s' % \
                              (cmd, plugin), secondary=plugin)
    return False

  # remove all commands for a plugin
  def api_removeplugin(self, plugin):
    """  remove all commands for a plugin
    @Yshort_name@w    = the plugin to remove commands for

    this function returns no values"""
    if plugin in self.cmds:
      del self.cmds[plugin]
    else:
      self.api('send.error')('removeplugin: plugin %s does not exist' % \
                                                        plugin)

  def format_cmdlist(self, category, cmdlist):
    """
    format a list of commands
    """
    tmsg = []
    for i in cmdlist:
      if i != 'default':
        tlist = self.cmds[category][i]['parser'].description.split('\n')
        if not tlist[0]:
          tlist.pop(0)
        tmsg.append('  @B%-10s@w : %s' % (i, tlist[0]))

    return tmsg

  def listcmds(self, category):
    """
    build a table of commands for a category
    """
    tmsg = []
    if category:
      if category in self.cmds:
        tmsg.append('Commands in %s:' % category)
        tmsg.append('@G' + '-' * 60 + '@w')
        groups = {}
        for i in sorted(self.cmds[category].keys()):
          if i != 'default':
            if self.cmds[category][i]['group'] not in groups:
              groups[self.cmds[category][i]['group']] = []

            groups[self.cmds[category][i]['group']].append(i)

        if len(groups) == 1:
          tmsg.extend(self.format_cmdlist(category,
                                          self.cmds[category].keys()))
        else:
          for group in sorted(groups.keys()):
            if group != 'Base':
              tmsg.append('@M' + '-' * 5 + ' ' +  group + ' ' + '-' * 5)
              tmsg.extend(self.format_cmdlist(category, groups[group]))
              tmsg.append('')

          tmsg.append('@M' + '-' * 5 + ' ' +  'Base' + ' ' + '-' * 5)
          tmsg.extend(self.format_cmdlist(category, groups['Base']))
        #tmsg.append('@G' + '-' * 60 + '@w')
    return tmsg

  def cmd_list(self, args):
    """
    list commands
    """
    tmsg = []
    category = args['category']
    cmd = args['cmd']
    if category:
      if category in self.cmds:
        if cmd and cmd in self.cmds[category]:
          msg = self.cmds[category][cmd]['parser'].format_help().split('\n')
          tmsg.extend(msg)
        else:
          tmsg.extend(self.listcmds(category))
      else:
        tmsg.append('There is no category %s' % category)
    else:
      tmsg.append('Categories:')
      tkeys = self.cmds.keys()
      tkeys.sort()
      tmsg.append(self.api('utils.listtocolumns')(tkeys, cols=3, columnwise=False, gap=6))
    return True, tmsg

  def cmd_runhistory(self, args):
    """
    act on the command history
    """
    if len(self.cmdhistory) < abs(args['number']):
      return True, ['# is outside of history length']

    if len(self.cmdhistory) >= self.api('setting.gets')('historysize'):
      cmd = self.cmdhistory[args['number'] - 1]
    else:
      cmd = self.cmdhistory[args['number']]

    self.api('send.client')('history: sending "%s"' % cmd)
    self.api('send.execute')(cmd)

    return True, []

  def cmd_history(self, args):
    """
    act on the command history
    """
    tmsg = []

    if args['clear']:
      del self.cmdhistorydict['history'][:]
      self.cmdhistorydict.sync()
      tmsg.append('Command history cleared')
    else:
      for i in self.cmdhistory:
        tmsg.append('%s : %s' % (self.cmdhistory.index(i), i))

    return True, tmsg

  def _savestate(self, _=None):
    """
    save states
    """
    self.cmdhistorydict.sync()
