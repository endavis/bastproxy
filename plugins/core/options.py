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

AUTOLOAD = True

class Plugin(BasePlugin):
  """
  a plugin to manage telnet options
  """
  def __init__(self, *args, **kwargs):
    """
    initialize the instance
    """
    BasePlugin.__init__(self, *args, **kwargs)

    self.canreload = False

    self.options = {}
    self.optionsmod = {}

    self.clientoptions = {}
    self.serveroptions = {}

    self.api('api.add')('addserveroption', self.api_addserveroption)
    self.api('api.add')('addclientoption', self.api_addclientoption)
    self.api('api.add')('prepareclient', self.api_prepareclient)
    self.api('api.add')('prepareserver', self.api_prepareserver)
    self.api('api.add')('resetoptions', self.api_resetoptions)

  # add a telnet option to the server
  def api_addserveroption(self, optionname, serveroption):
    """  add a server option
    @Yserveroption@w  = server option to add, must be of
                                        class BaseTelnetOption
    """
    if issubclass(serveroption, BaseTelnetOption):
      self.api('send.msg')('adding telnet option %s to server' % \
                                                              optionname)
      self.serveroptions[optionname] = serveroption
      return True
    return False

  # add a telnet option to the client
  def api_addclientoption(self, optionname, clientoption):
    """  add a client option
    @Yclientoption@w  = client option to add, must be of
                                        class BaseTelnetOption
    """
    if issubclass(clientoption, BaseTelnetOption):
      self.api('send.msg')('adding telnet option %s to client' % \
                                                              optionname)
      self.clientoptions[optionname] = clientoption
      return True
    return False

  def load(self):
    """
    load the module
    """
    BasePlugin.load(self)
    #self.api('events.register')('plugin_loaded', self.plugin_loaded)
    self.api('log.console')(self.sname)

  def plugin_loaded(self, args):
    """
    check to see if this plugin has SERVER and CLIENT
    """
    plugin = args['plugin']
    module = self.api('plugins.module')(plugin)

    if hasattr(module, 'SERVER'):
      self.options[plugin] = True
      self.optionsmod[plugin] = module
      self.api('send.msg')('adding %s as a telnet option' % plugin,
                               secondary=plugin)

  def reloadmod(self, mod):
    """
    reload a module
    """
    self.api('events.eraise')('OPTRELOAD', {'option':mod})

  # prepare the client to process telnet options
  def api_prepareclient(self, client):
    """
    add an option to a client
    """
    for i in self.clientoptions:
      try:
        self.clientoptions[i](client)
      except AttributeError:
        self.api('send.msg')('Did not add option to client: %s' % i,
                                 'telopt')

  # prepare the server to process telnet options
  def api_prepareserver(self, server):
    """
    add an option to a server
    """
    for i in self.serveroptions:
      try:
        self.serveroptions[i](server)
      except AttributeError:
        self.api('send.msg')('Did not add option to server: %s' % i,
                                 'telopt')

  # reset options
  def api_resetoptions(self, server, onclose=False):
    # pylint: disable=no-self-use
    """
    reset options
    """
    for i in server.option_handlers:
      if i in server.options:
        server.option_handlers[i].reset(onclose)

