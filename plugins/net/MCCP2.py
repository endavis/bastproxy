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

    self.api('dependency:add')('net.options')

    self.can_reload_f = False

    self.option_name = 'MCCP2'
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
    self.api('net.options:client:option:add')(self.plugin_id, self.option_name, self.option_num, CLIENT)

class SERVER(BaseTelnetOption):
  """
  the mccp option class to connect to a server
  """
  def __init__(self, telnet_object, option_name, option_number, plugin_id):
    """
    initialize the instance
    """
    BaseTelnetOption.__init__(self, telnet_object, option_name, option_number, plugin_id)
    #self.telnet_object.debug_types.append(self.option_name)

    self.orig_readdatafromsocket = None
    self.zlib_decomp = None

  def handleopt(self, command, sbdata):
    """
    handle the mccp opt
    """
    self.telnet_object.msg('%s - in handleopt' % (ord(command)),
                           mtype=self.option_name)
    if command == WILL:
      self.telnet_object.msg('sending IAC DO MCCP2 (%s)' % self.option_number, mtype=self.option_name)
      self.telnet_object.send("".join([IAC, DO, self.option_string]))

    elif command in [SE, SB]:
      self.telnet_object.msg('got an SE mccp in handleopt',
                             mtype=self.option_name)
      self.telnet_object.msg('starting compression with server',
                             mtype=self.option_name)
      self.telnet_object.options[ord(self.option_string)] = True
      self.negotiate()

  def negotiate(self):
    """
    negotiate the mccp opt
    """
    self.telnet_object.msg('negotiating', mtype=self.option_name)
    self.zlib_decomp = zlib.decompressobj(15)
    # decompress the raw queue
    if self.telnet_object.rawq:
      self.telnet_object.msg('converting rawq in handleopt',
                             mtype=self.option_name)
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

      self.telnet_object.msg('decompressing', mtype=self.option_name)

      # now do our work when returning the data
      return self.zlib_decomp.decompress(data)

    setattr(self.telnet_object, 'readdatafromsocket', mccp_readdatafromsocket)

  def reset(self, onclose=False):
    """
    resetting the option
    """
    self.telnet_object.msg('resetting', mtype=self.option_name)
    self.telnet_object.addtooutbuffer("".join([IAC, DONT, self.option_string]), True)
    self.telnet_object.rawq = self.zlib_decomp.decompress(self.telnet_object.rawq)
    setattr(self.telnet_object, 'readdatafromsocket',
            self.orig_readdatafromsocket)
    BaseTelnetOption.reset(self)

class CLIENT(BaseTelnetOption):
  """
  a class to connect to a client to manage mccp
  """
  def __init__(self, telnet_object, option_name, option_number, plugin_id):
    """
    initialize the instance
    """
    BaseTelnetOption.__init__(self, telnet_object, option_name, option_number, plugin_id)

    self.option_num = option_number
    self.option_string = chr(self.option_num)

    self.orig_convert_outdata = None
    self.zlib_comp = None
    self.telnet_object.msg('sending IAC WILL MCCP2 (%s)' % self.option_number, mtype=self.option_name)
    self.telnet_object.send("".join([IAC, WILL, self.option_string]))
    #self.telnet_object.debug_types.append(self.option_name)

  def handleopt(self, command, sbdata):
    """
    handle the mccp option
    """
    self.telnet_object.msg('%s - in handleopt' % (ord(command)),
                           mtype=self.option_name)

    if command == DO:
      self.telnet_object.options[ord(self.option_string)] = True
      self.negotiate()

  def negotiate(self):
    """
    negotiate the mccp option
    """
    self.telnet_object.msg("starting mccp", level=2, mtype=self.option_name)
    self.telnet_object.msg('sending IAC SB MCCP2 (%s) IAC SE' % self.option_number, mtype=self.option_name)
    self.telnet_object.send("".join([IAC, SB, self.option_string, IAC, SE]))

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
      self.telnet_object.msg('compressing', mtype=self.option_name)
      return "".join([self.zlib_comp.compress(data),
                      self.zlib_comp.flush(zlib.Z_SYNC_FLUSH)])

    setattr(self.telnet_object, 'convert_outdata', mccp_convert_outdata)

  def reset(self, onclose=False):
    """
    reset the option
    """
    self.telnet_object.msg('resetting', mtype=self.option_name)
    if not onclose:
      self.telnet_object.addtooutbuffer("".join([IAC, DONT, self.option_string]), True)
    setattr(self.telnet_object, 'convert_outdata', self.orig_convert_outdata)
    self.telnet_object.outbuffer = \
                        self.zlib_comp.uncompress(self.telnet_object.outbuffer)
    BaseTelnetOption.reset(self)
