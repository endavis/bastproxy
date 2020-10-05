"""
this module handles telnet option 25, Terminal Type
"""
from libs.net._basetelnetoption import BaseTelnetOption
from libs.net.telnetlib import WILL, DO, IAC, SE, SB, DONT, NOOPT, CODES
from plugins._baseplugin import BasePlugin

NAME = 'Term Type Telnet Option'
SNAME = 'TERMTYPE'
PURPOSE = 'Handle telnet option 24, terminal type'
AUTHOR = 'Bast'
VERSION = 1
PRIORITY = 35

REQUIRED = True

# Plugin
class Plugin(BasePlugin):
  """
  the plugin to handle the Terminal Type telnet option
  """
  def __init__(self, *args, **kwargs):
    # pylint: disable=too-many-arguments
    """
    initialize the class
    """
    BasePlugin.__init__(self, *args, **kwargs)

    self.api('dependency:add')('net.options')

    self.can_reload_f = False

    self.option_name = 'TERMTYPE'
    self.option_num = 86
    self.option_string = chr(self.option_num)
    self.option_code = '<%s>' % self.option_name

    CODES[self.option_num] = self.option_code

  def initialize(self):
    """
    initialize the plugin
    """
    BasePlugin.initialize(self)

    self.api('net.options:server:option:add')(self.plugin_id, self.option_name, self.option_num, SERVER)
    self.api('net.options:client:option:add')(self.plugin_id, self.option_name, self.option_num, SERVER)

class SERVER(BaseTelnetOption):
  """
  the termtype class for the server
  """
  def __init__(self, telnet_object, option_name, option_number, plugin_id):
    """
    initialize the instance
    """
    BaseTelnetOption.__init__(self, telnet_object, option_name, option_number, plugin_id)
    #self.telnet_object.debug_types.append('TTYPE')

  def handleopt(self, command, sbdata):
    """
    handle the opt
    """
    self.telnet_object.msg('%s - in handleopt' % self.telnet_object.ccode(command),
                           mtype=self.option_name)
    if command == DO:
      self.telnet_object.msg(
          'sending IAC SB TTYPE NOOPT MUSHclient-Aard IAC SE',
          mtype=self.option_name)
      self.telnet_object.send(
          "".join([IAC, SB, self.option_string, NOOPT, self.telnet_object.ttype, IAC, SE]))


class CLIENT(BaseTelnetOption):
  """
  the termtype class for the client
  """
  def __init__(self, telnet_object, option_name, option_number, plugin_id):
    """
    initialize the instance
    """
    BaseTelnetOption.__init__(self, telnet_object, option_name, option_number, plugin_id)
    #self.telnet_object.debug_types.append(self.option_name)
    self.telnet_object.msg('sending IAC WILL TTYPE', mtype=self.option_name)
    self.telnet_object.addtooutbuffer("".join([IAC, DO, self.option_string]), True)

  def handleopt(self, command, sbdata):
    """
    handle the opt
    """
    self.telnet_object.msg('%s - in handleopt: %s' % \
                               (self.telnet_object.ccode(command), sbdata),
                           mtype=self.option_name)

    if command == WILL:
      self.telnet_object.addtooutbuffer(
          "".join([IAC, SB, self.option_string, chr(1), IAC, SE]), True)
    elif command in [SE, SB]:
      self.telnet_object.ttype = sbdata.strip()

  def negotiate(self):
    """
    negotiate when receiving an op
    """
    self.telnet_object.msg("starting TTYPE", level=2, mtype=self.option_name)
    self.telnet_object.msg('sending IAC SB TTYPE IAC SE', mtype=self.option_name)
    self.telnet_object.send("".join([IAC, SB, self.option_string, IAC, SE]))

  def reset(self, onclose=False):
    """
    reset the opt
    """
    self.telnet_object.msg('resetting', mtype=self.option_name)
    if not onclose:
      self.telnet_object.addtooutbuffer("".join([IAC, DONT, self.option_string]), True)
    BaseTelnetOption.reset(self)
