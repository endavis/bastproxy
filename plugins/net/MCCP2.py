"""
This module handles telnet option 86, MCCP v2
"""
import zlib
from libs.net._basetelnetoption import BaseTelnetOption
from libs.net.telnetlib import WILL, DO, IAC, SE, SB, DONT, CODES
from plugins._baseplugin import BasePlugin

NAME = 'MCCP2'
SNAME = 'MCCP2'
PURPOSE = 'Handle telnet option 86, MCCP2'
AUTHOR = 'Bast'
VERSION = 1
PRIORITY = 35

REQUIRED = True

MCCP2 = chr(86)  # Mud Compression Protocol, v2

CODES[86] = '<MCCP2>'

# Plugin
class Plugin(BasePlugin):
  """
  the plugin to handle MCCP
  """
  def __init__(self, *args, **kwargs):
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
  the mccp option class to connect to a server
  """
  def __init__(self, telnet_object):
    """
    initialize the instance
    """
    BaseTelnetOption.__init__(self, telnet_object, MCCP2, SNAME)
    #self.telnet_object.debug_types.append('MCCP2')
    self.orig_readdatafromsocket = None
    self.zlib_decomp = None

  def handleopt(self, command, sbdata):
    """
    handle the mccp opt
    """
    self.telnet_object.msg('%s - in handleopt' % (ord(command)),
                           mtype='MCCP2')
    if command == WILL:
      self.telnet_object.msg('sending IAC DO MCCP2', mtype='MCCP2')
      self.telnet_object.send("".join([IAC, DO, MCCP2]))

    elif command in [SE, SB]:
      self.telnet_object.msg('got an SE mccp in handleopt',
                             mtype='MCCP2')
      self.telnet_object.msg('starting compression with server',
                             mtype='MCCP2')
      self.telnet_object.options[ord(MCCP2)] = True
      self.negotiate()

  def negotiate(self):
    """
    negotiate the mccp opt
    """
    self.telnet_object.msg('negotiating', mtype='MCCP2')
    self.zlib_decomp = zlib.decompressobj(15)
    # decompress the raw queue
    if self.telnet_object.rawq:
      self.telnet_object.msg('converting rawq in handleopt',
                             mtype='MCCP2')
      try:
        rawq = self.zlib_decomp.decompress(self.telnet_object.rawq)
        self.telnet_object.rawq = rawq
        self.telnet_object.process_rawq()
      except Exception: # pylint: disable=broad-except
        self.telnet_object.handle_error()

    # replace the readdatafromsocket function with one that decompresses the stream
    orig_readdatafromsocket = self.telnet_object.readdatafromsocket
    self.orig_readdatafromsocket = orig_readdatafromsocket
    def mccp_readdatafromsocket():
      """
      decompress the data
      """
      # give the original func a chance to munge the data
      data = orig_readdatafromsocket()

      self.telnet_object.msg('decompressing', mtype='MCCP2')

      # now do our work when returning the data
      return self.zlib_decomp.decompress(data)

    setattr(self.telnet_object, 'readdatafromsocket', mccp_readdatafromsocket)

  def reset(self, onclose=False):
    """
    resetting the option
    """
    self.telnet_object.msg('resetting', mtype='MCCP2')
    self.telnet_object.addtooutbuffer("".join([IAC, DONT, MCCP2]), True)
    self.telnet_object.rawq = self.zlib_decomp.decompress(self.telnet_object.rawq)
    setattr(self.telnet_object, 'readdatafromsocket',
            self.orig_readdatafromsocket)
    BaseTelnetOption.reset(self)

class CLIENT(BaseTelnetOption):
  """
  a class to connect to a client to manage mccp
  """
  def __init__(self, telnet_object):
    """
    initialize the instance
    """
    BaseTelnetOption.__init__(self, telnet_object, MCCP2, SNAME)
    self.orig_convert_outdata = None
    self.zlib_comp = None
    self.telnet_object.msg('sending IAC WILL MCCP2', mtype='MCCP2')
    self.telnet_object.send("".join([IAC, WILL, MCCP2]))

  def handleopt(self, command, sbdata):
    """
    handle the mccp option
    """
    self.telnet_object.msg('%s - in handleopt' % (ord(command)),
                           mtype='MCCP2')

    if command == DO:
      self.telnet_object.options[ord(MCCP2)] = True
      self.negotiate()

  def negotiate(self):
    """
    negotiate the mccp option
    """
    self.telnet_object.msg("starting mccp", level=2, mtype='MCCP2')
    self.telnet_object.msg('sending IAC SB MCCP2 IAC SE', mtype='MCCP2')
    self.telnet_object.send("".join([IAC, SB, MCCP2, IAC, SE]))

    self.zlib_comp = zlib.compressobj(9)
    self.telnet_object.outbuffer = \
                      self.zlib_comp.compress(self.telnet_object.outbuffer)

    orig_convert_outdata = self.telnet_object.convert_outdata
    self.orig_convert_outdata = orig_convert_outdata

    def mccp_convert_outdata(data):
      """
      compress outgoing data
      """
      data = orig_convert_outdata(data)
      self.telnet_object.msg('compressing', mtype='MCCP2')
      return "".join([self.zlib_comp.compress(data),
                      self.zlib_comp.flush(zlib.Z_SYNC_FLUSH)])

    setattr(self.telnet_object, 'convert_outdata', mccp_convert_outdata)

  def reset(self, onclose=False):
    """
    reset the option
    """
    self.telnet_object.msg('resetting', mtype='MCCP2')
    if not onclose:
      self.telnet_object.addtooutbuffer("".join([IAC, DONT, MCCP2]), True)
    setattr(self.telnet_object, 'convert_outdata', self.orig_convert_outdata)
    self.telnet_object.outbuffer = \
                        self.zlib_comp.uncompress(self.telnet_object.outbuffer)
    BaseTelnetOption.reset(self)
