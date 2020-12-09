"""
This module holds the class that manages Telnet Options as well as an
instance of the class
"""
from plugins._baseplugin import BasePlugin
from libs.net._basetelnetoption import BaseTelnetOption

NAME = 'Option Handler'
SNAME = 'options'
PURPOSE = 'Handle Telnet Options'
AUTHOR = 'Bast'
VERSION = 1
PRIORITY = 7

REQUIRED = True

class Plugin(BasePlugin):
  """
  a plugin to manage telnet options
  """
  def __init__(self, *args, **kwargs):
    """
    initialize the instance
    """
    BasePlugin.__init__(self, *args, **kwargs)

    self.can_reload_f = False

    self.options = {}
    self.optionsmod = {}

    self.clientoptions = {}
    self.serveroptions = {}

    # new api format
    self.api('libs.api:add')('server:option:add', self.api_addserveroption)
    self.api('libs.api:add')('client:option:add', self.api_addclientoption)
    self.api('libs.api:add')('client:prepare', self.api_prepareclient)
    self.api('libs.api:add')('server:prepare', self.api_prepareserver)
    self.api('libs.api:add')('options:reset', self.api_resetoptions)

    self.dependencies = ['core.events', 'core.log', 'core.errors']

  # add a telnet option to the server
  def api_addserveroption(self, plugin_id, option_name, option_num, option_class):
    """  add a server option
    @Yserveroption@w  = server option to add, must be of
                                        class BaseTelnetOption
    """
    if issubclass(option_class, BaseTelnetOption):
      self.api('send:msg')('adding telnet option %s to server' % \
                                                              option_name)
      option_data = {}
      option_data['plugin_id'] = plugin_id
      option_data['optionname'] = option_name
      option_data['optionclass'] = option_class
      option_data['optionnum'] = option_num
      self.serveroptions[option_name] = option_data
      return True
    return False

  # add a telnet option to the client
  def api_addclientoption(self, plugin_id, option_name, option_num, option_class):
    """  add a client option
    @Yclientoption@w  = client option to add, must be of
                                        class BaseTelnetOption
    """
    if issubclass(option_class, BaseTelnetOption):
      self.api('send:msg')('adding telnet option %s to client' % \
                                                              option_name)
      option_data = {}
      option_data['plugin_id'] = plugin_id
      option_data['optionname'] = option_name
      option_data['optionclass'] = option_class
      option_data['optionnum'] = option_num
      self.clientoptions[option_name] = option_data
      return True
    return False

  def initialize(self):
    """
    initialize the plugin
    """
    BasePlugin.initialize(self)
    self.api('core.log:toggle:to:console')(self.plugin_id)

  def plugin_loaded(self, args):
    """
    check to see if this plugin has SERVER and CLIENT
    """
    plugin = args['plugin']
    module = self.api('core.plugins:get:plugin:module')(plugin)

    if hasattr(module, 'SERVER'):
      self.options[plugin] = True
      self.optionsmod[plugin] = module
      self.api('send:msg')('adding %s as a telnet option' % plugin)

  def reloadmod(self, mod):
    """
    reload a module
    """
    self.api('core.events:raise:event')('OPTRELOAD', {'option':mod})

  # prepare the client to process telnet options
  def api_prepareclient(self, client):
    """
    add an option to a client
    """
    for plugin_id in self.clientoptions:
      try:
        self.clientoptions[plugin_id]['optionclass'](client, self.clientoptions[plugin_id]['optionname'],
                                                     self.clientoptions[plugin_id]['optionnum'], plugin_id)
      except AttributeError:
        self.api('send:traceback')('Did not add option %s to client' % plugin_id)

  # prepare the server to process telnet options
  def api_prepareserver(self, server):
    """
    add an option to a server
    """
    for plugin_id in self.serveroptions:
      try:
        # self, telnet_object, option_name, option_number, plugin_id
        self.serveroptions[plugin_id]['optionclass'](server, self.serveroptions[plugin_id]['optionname'],
                                                     self.serveroptions[plugin_id]['optionnum'], plugin_id)
      except AttributeError:
        self.api('send:traceback')('Did not add option %s to server' % plugin_id)

  # reset options
  def api_resetoptions(self, server, onclose=False):
    # pylint: disable=no-self-use
    """
    reset options
    """
    for i in server.option_handlers:
      if i in server.options:
        server.option_handlers[i].reset(onclose)
