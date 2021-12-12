"""
a plugin to handle global variables, if something goes through
  send.execute (this includes from the client), a variable
  can be specified with $varname and will be substituted.
"""
import os
from string import Template
from plugins._baseplugin import BasePlugin
import libs.argp as argp
from libs.persistentdict import PersistentDict

#these 5 are required
NAME = 'Variables'
SNAME = 'vars'
PURPOSE = 'create variables'
AUTHOR = 'Bast'
VERSION = 1
PRIORITY = 25

REQUIRED = True


class Plugin(BasePlugin):
  """
  a plugin to handle global variables, if something goes through
   send.execute (this includes from the client), a variable
   can be specified with $varname and will be substituted.
  """
  def __init__(self, *args, **kwargs):
    """
    initialize the instance
    """
    BasePlugin.__init__(self, *args, **kwargs)

    self.variablefile = os.path.join(self.save_directory, 'variables.txt')
    self._variables = PersistentDict(self.variablefile, 'c')
    self.api('libs.api:add')('get', self.api_getv)
    self.api('libs.api:add')('set', self.api_setv)
    self.api('libs.api:add')('replace', self.api_replace)

  def initialize(self):
    """
    initialize the plugin
    """
    BasePlugin.initialize(self)

    parser = argp.ArgumentParser(add_help=False,
                                 description='add a variable')
    parser.add_argument('name',
                        help='the name of the variable',
                        default='',
                        nargs='?')
    parser.add_argument('value',
                        help='the value of the variable',
                        default='',
                        nargs='?')
    self.api('core.commands:command:add')('add',
                                          self.cmd_add,
                                          parser=parser)

    parser = argp.ArgumentParser(add_help=False,
                                 description='remove a variable')
    parser.add_argument('name',
                        help='the variable to remove',
                        default='',
                        nargs='?')
    self.api('core.commands:command:add')('remove',
                                          self.cmd_remove,
                                          parser=parser)

    parser = argp.ArgumentParser(add_help=False,
                                 description='list variables')
    parser.add_argument('match',
                        help='list only variables that have this argument in their name',
                        default='',
                        nargs='?')
    self.api('core.commands:command:add')('list',
                                          self.cmd_list,
                                          parser=parser)

    # self.api('commands.default')('list')

    self.api('core.events:register:to:event')('io_execute_event',
                                              self.checkline,
                                              prio=99)
    self.api('core.events:register:to:event')('io_execute_event',
                                              self.checkline,
                                              prio=1)
    self.api('core.events:register:to:event')('ev_{0.plugin_id}_savestate'.format(self), self._savestate)

  # get a variable
  def api_getv(self, varname):
    """  get the variable with a specified name
    @Yvarname@w  = the variable to get

    this function returns the value of variable with the name of the argument
    """
    if varname in self._variables:
      return self._variables[varname]

    return None

  # set a variable
  def api_setv(self, varname, value):
    """  set the variable with a specified name to the specified value
    @Yvarname@w  = the variable to set
    @Yvalue@w  = the value to set

    this function returns True if the value was set, False if an error was
    encountered
    """
    try:
      self._variables[varname] = value
      return True
    except Exception: # pylint: disable=broad-except
      return False

  # replace variables in data
  def api_replace(self, data):
    """replace the variables in data
    @Ydata@w  = the variable to get

    this function returns the data after variable substition
    """
    templ = Template(data)
    return templ.safe_substitute(self._variables)

  def checkline(self, args):
    """
    this function checks for variables in input
    """
    data = args['fromdata'].strip()

    datan = self.api('client.vars:replace')(data)

    if datan != data:
      self.api('libs.io:trace:add:execute')(self.plugin_id, 'Modify',
                                            original_data=data,
                                            new_data=datan)

      self.api('libs.io:send:msg')('replacing "%s" with "%s"' % (data.strip(),
                                                                 datan.strip()))
      args['fromdata'] = datan

    return args

  def cmd_add(self, args):
    """
    command to add a variable
    """
    tmsg = []
    if args['name'] and args['value']:
      tmsg.append("@GAdding variable@w : '%s' will be replaced by '%s'" % \
                                              (args['name'], args['value']))
      self.addvariable(args['name'], args['value'])
      return True, tmsg

    tmsg.append("@RPlease include all arguments@w")
    return False, tmsg

  def cmd_remove(self, args):
    """
    command to remove a variable
    """
    tmsg = []
    if args['name']:
      tmsg.append("@GRemoving variable@w : '%s'" % (args['name']))
      self.removevariable(args['name'])
      return True, tmsg

    return False, ['@RPlease specifiy a variable to remove@w']

  def cmd_list(self, args):
    """
    command to list variables
    """
    tmsg = self.listvariables(args['match'])
    return True, tmsg

  def addvariable(self, item, value):
    """
    internally add a variable
    """
    self._variables[item] = value
    self._variables.sync()

  def removevariable(self, item):
    """
    internally remove a variable
    """
    if item in self._variables:
      del self._variables[item]
      self._variables.sync()

  def listvariables(self, match):
    """
    return a table of variables
    """
    tmsg = []
    for item in self._variables:
      if not match or match in item:
        tmsg.append("%-20s : %s@w" % (item, self._variables[item]))
    if not tmsg:
      tmsg = ['None']
    return tmsg

  def clearvariables(self):
    """
    clear all variables
    """
    self._variables.clear()
    self._variables.sync()

  def reset(self):
    """
    reset the plugin
    """
    BasePlugin.reset(self)
    self.clearvariables()

  def _savestate(self, _=None):
    """
    save states
    """
    self._variables.sync()
