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
  def __init__(self, telnetobj):
    """
    initialize the instance
    """
    BaseTelnetOption.__init__(self, telnetobj, TTYPE, SNAME)
    #self.telnetobj.debug_types.append('TTYPE')

  def handleopt(self, command, sbdata):
    """
    handle the opt
    """
    self.telnetobj.msg('%s - in handleopt' % self.telnetobj.ccode(command),
                       mtype='TTYPE')
    if command == DO:
      self.telnetobj.msg(
          'sending IAC SB TTYPE NOOPT MUSHclient-Aard IAC SE',
          mtype='TTYPE')
      self.telnetobj.send(
          "".join([IAC, SB, TTYPE, NOOPT, self.telnetobj.ttype, IAC, SE]))


class CLIENT(BaseTelnetOption):
  """
  the termtype class for the client
  """
  def __init__(self, telnetobj):
    """
    initialize the instance
    """
    BaseTelnetOption.__init__(self, telnetobj, TTYPE, SNAME)
    #self.telnetobj.debug_types.append('TTYPE')
    self.telnetobj.msg('sending IAC WILL TTYPE', mtype='TTYPE')
    self.telnetobj.addtooutbuffer("".join([IAC, DO, TTYPE]), True)

  def handleopt(self, command, sbdata):
    """
    handle the opt
    """
    self.telnetobj.msg('%s - in handleopt: %s' % \
                         (self.telnetobj.ccode(command), sbdata),
                       mtype='TTYPE')

    if command == WILL:
      self.telnetobj.addtooutbuffer(
          "".join([IAC, SB, TTYPE, chr(1), IAC, SE]), True)
    elif command in [SE, SB]:
      self.telnetobj.ttype = sbdata.strip()

  def negotiate(self):
    """
    negotiate when receiving an op
    """
    self.telnetobj.msg("starting TTYPE", level=2, mtype='TTYPE')
    self.telnetobj.msg('sending IAC SB TTYPE IAC SE', mtype='TTYPE')
    self.telnetobj.send("".join([IAC, SB, TTYPE, IAC, SE]))

  def reset(self, onclose=False):
    """
    reset the opt
    """
    self.telnetobj.msg('resetting', mtype='TTYPE')
    if not onclose:
      self.telnetobj.addtooutbuffer("".join([IAC, DONT, TTYPE]), True)
    BaseTelnetOption.reset(self)
