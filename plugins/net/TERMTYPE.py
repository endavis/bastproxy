"""
this module handles telnet option 25, Terminal Type
"""
from libs.net._basetelnetoption import BaseTelnetOption
from libs.net.telnetlib import WILL, DO, IAC, SE, SB, DONT, NOOPT, CODES
from plugins._baseplugin import BasePlugin

NAME = 'Term Type Telnet Option'
SNAME = 'TTYPE'
PURPOSE = 'Handle telnet option 24, terminal type'
AUTHOR = 'Bast'
VERSION = 1
PRIORITY = 35

REQUIRED = True

TTYPE = chr(24)  # Terminal Type

CODES[24] = "<TERMTYPE>"

# Plugin
class Plugin(BasePlugin):
  """
  the plugin to handle the Terminal Type telnet option
  """
  def __init__(self, *args, **kwargs):
    # pylint: disable=too-many-arguments
    """
    Iniitilaize the class
    """
    BasePlugin.__init__(self, *args, **kwargs)

    self.api('dependency.add')('net.options')

    self.can_reload_f = False

  def initialize(self):
    BasePlugin.initialize(self)

    self.api('options.addserveroption')(self.short_name, SERVER)
    self.api('options.addclientoption')(self.short_name, CLIENT)

class SERVER(BaseTelnetOption):
  """
  the termtype class for the server
  """
  def __init__(self, telnet_object):
    """
    initialize the instance
    """
    BaseTelnetOption.__init__(self, telnet_object, TTYPE, SNAME)
    #self.telnet_object.debug_types.append('TTYPE')

  def handleopt(self, command, sbdata):
    """
    handle the opt
    """
    self.telnet_object.msg('%s - in handleopt' % self.telnet_object.ccode(command),
                           mtype='TTYPE')
    if command == DO:
      self.telnet_object.msg(
          'sending IAC SB TTYPE NOOPT MUSHclient-Aard IAC SE',
          mtype='TTYPE')
      self.telnet_object.send(
          "".join([IAC, SB, TTYPE, NOOPT, self.telnet_object.ttype, IAC, SE]))


class CLIENT(BaseTelnetOption):
  """
  the termtype class for the client
  """
  def __init__(self, telnet_object):
    """
    initialize the instance
    """
    BaseTelnetOption.__init__(self, telnet_object, TTYPE, SNAME)
    #self.telnet_object.debug_types.append('TTYPE')
    self.telnet_object.msg('sending IAC WILL TTYPE', mtype='TTYPE')
    self.telnet_object.addtooutbuffer("".join([IAC, DO, TTYPE]), True)

  def handleopt(self, command, sbdata):
    """
    handle the opt
    """
    self.telnet_object.msg('%s - in handleopt: %s' % \
                               (self.telnet_object.ccode(command), sbdata),
                           mtype='TTYPE')

    if command == WILL:
      self.telnet_object.addtooutbuffer(
          "".join([IAC, SB, TTYPE, chr(1), IAC, SE]), True)
    elif command in [SE, SB]:
      self.telnet_object.ttype = sbdata.strip()

  def negotiate(self):
    """
    negotiate when receiving an op
    """
    self.telnet_object.msg("starting TTYPE", level=2, mtype='TTYPE')
    self.telnet_object.msg('sending IAC SB TTYPE IAC SE', mtype='TTYPE')
    self.telnet_object.send("".join([IAC, SB, TTYPE, IAC, SE]))

  def reset(self, onclose=False):
    """
    reset the opt
    """
    self.telnet_object.msg('resetting', mtype='TTYPE')
    if not onclose:
      self.telnet_object.addtooutbuffer("".join([IAC, DONT, TTYPE]), True)
    BaseTelnetOption.reset(self)
