"""
$Id$

this module holds the proxy client class
"""
import time

from libs.net.telnetlib import Telnet

PASSWORD = 0
CONNECTED = 1

class Client(Telnet):
  """
  a class to hand a proxy client
  """
  def __init__(self, sock, host, port):
    """
    init the class
    """
    Telnet.__init__(self, host=host, port=port, sock=sock)

    self.ttype = 'Client'
    self.connectedtime = None
    self.pwtries = 0
    self.banned = False
    self.viewonly = False

    if sock:
      self.connected = True
      self.connectedtime = time.localtime()

    self.api('events.register')('to_client_event',
                                self.addtooutbufferevent, prio=99)

    self.api('options.prepareclient')(self)

    self.state = PASSWORD
    self.addtooutbufferevent({'original':self.api('colors.convertcolors')(
        '%s%s@w: %sPlease enter the proxy password:@w' % (self.api('proxy.preambleerrorcolor')(),
                                                          self.api('proxy.preamble')(),
                                                          self.api('proxy.preambleerrorcolor')())),
                              'dtype':'passwd'})

  def addtooutbufferevent(self, args):
    """
    this function adds to the output buffer
    """
    if 'client' in args and args['client'] and args['client'] != self:
      return

    outbuffer = args['original']
    dtype = None
    raw = False
    if 'dtype' in args:
      dtype = args['dtype']
    if not dtype:
      dtype = 'fromproxy'
    if 'raw' in args:
      raw = args['raw']
    if outbuffer != None:
      if (dtype == 'fromproxy' or dtype == 'frommud') \
            and self.state == CONNECTED:
        outbuffer = "".join([outbuffer, '\r\n'])
        Telnet.addtooutbuffer(self, outbuffer, raw)
      elif len(dtype) == 1 and ord(dtype) in self.options \
            and self.state == CONNECTED:
        Telnet.addtooutbuffer(self, outbuffer, raw)
      elif dtype == 'passwd' and self.state == PASSWORD:
        outbuffer = "".join([outbuffer, '\r\n'])
        Telnet.addtooutbuffer(self, outbuffer, raw)

  def handle_read(self):
    """
    handle a read
    """
    if not self.connected:
      return
    Telnet.handle_read(self)

    data = self.getdata()

    if data:
      if self.state == CONNECTED:
        if self.viewonly:
          self.addtooutbufferevent(
              {'todata':self.api('colors.convertcolors')(
                  '%s%s@w: %sYou are in view mode!@w' % (self.api('proxy.preambleerrorcolor')(),
                                                         self.api('proxy.preamble')(),
                                                         self.api('proxy.preambleerrorcolor')()))})
        else:
          if data:
            self.api('send.execute')(data, fromclient=True)

      elif self.state == PASSWORD:
        data = data.strip()
        proxyp = self.api('plugins.getp')('proxy')
        dpw = proxyp.api('proxy.proxypw')()
        vpw = proxyp.api('proxy.proxypwview')()

        if dpw and  data == dpw:
          self.api('send.msg')('Successful password from %s : %s' % \
                                            (self.host, self.port), 'net')
          self.state = CONNECTED
          self.api('events.eraise')('client_connected', {'client':self},
                                    calledfrom="client")
          self.api('send.client')("%s - %s: Client Connected" % \
                                      (self.host, self.port))
        elif vpw and data == vpw:
          self.api('send.msg')('Successful view password from %s : %s' % \
                              (self.host, self.port), 'net')
          self.state = CONNECTED
          self.viewonly = True
          self.addtooutbufferevent(
              {'original':self.api('colors.convertcolors')(
                  '%s%s@W: @GYou are connected in view mode@w' % (self.api('proxy.preambleerrorcolor')(),
                                                                  self.api('proxy.preamlbe')()))})
          self.api('events.eraise')('client_connected_view',
                                    {'client':self}, calledfrom="client")
          self.api('send.client')(
              "%s - %s: Client Connected (View Mode)" % \
                  (self.host, self.port))
        else:
          self.pwtries += 1
          if self.pwtries == 5:
            self.addtooutbufferevent(
                {'original':self.api('colors.convertcolors')(
                    '%s%s@w: %sYou have been BANNED for 10 minutes:@w' % (self.api('proxy.preambleerrorcolor')(),
                                                                          self.api('proxy.preamble')(),
                                                                          self.api('proxy.preambleerrorcolor')())),
                 'dtype':'passwd'})
            self.api('send.msg')('%s has been banned.' % self.host, 'net')
            self.api('clients.addbanned')(self.host)
            self.handle_close()
          else:
            self.addtooutbufferevent(
                {'original':self.api('colors.convertcolors')(
                    '%s%s@w: %sPlease try again! Proxy Password:@w' % (self.api('proxy.preambleerrorcolor')(),
                                                                       self.api('proxy.preamble')(),
                                                                       self.api('proxy.preambleerrorcolor')())),
                 'dtype':'passwd'})

  def handle_close(self):
    """
    handle a close
    """
    self.api('send.client')("%s - %s: Client Disconnected" % \
                                (self.host, self.port))
    self.api('send.msg')("%s - %s: Client Disconnected" % \
                                (self.host, self.port), primary='net')
    self.api('events.eraise')('client_disconnected', {'client':self}, calledfrom="client")
    self.api('events.unregister')('to_client_event', self.addtooutbufferevent)
    while self.outbuffer:
      self.handle_write()
    Telnet.handle_close(self)
