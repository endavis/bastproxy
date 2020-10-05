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

    self.terminal_type = 'Client'
    self.bad_password_count = 0
    self.banned = False
    self.view_only = False
    self.state = PASSWORD

    if sock:
      self.connected = True
      self.connected_time = time.localtime()

    self.api('core.events:register:to:event')('to_client_event',
                                              self.addtooutbufferevent, prio=99)

    self.api('net.options:client:prepare')(self)

    self.addtooutbufferevent({'original':self.api('core.colors:colorcode:to:ansicode')(
        '%s%s@w: %sPlease enter the proxy password:@w' % (self.api('net.proxy:preamble:error:color:get')(),
                                                          self.api('net.proxy:preamble:get')(),
                                                          self.api('net.proxy:preamble:error:color:get')())),
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
        if self.view_only:
          self.addtooutbufferevent(
              {'todata':self.api('core.colors:colorcode:to:ansicode')(
                  '%s%s@w: %sYou are in view mode!@w' % (self.api('net.proxy:preamble:error:color:get')(),
                                                         self.api('net.proxy:preamble')(),
                                                         self.api('net.proxy:preamble:error:color:get')()))})
        else:
          if data:
            self.api('send:execute')(data, fromclient=True)

      elif self.state == PASSWORD:
        data = data.strip()
        proxyp = self.api('core.plugins:get:plugin:instance')('net.proxy')
        dpw = proxyp.api('net.proxy:ssc:proxypw')()
        vpw = proxyp.api('net.proxy:ssc:proxypwview')()

        if dpw and  data == dpw:
          self.api('send:msg')('Successful password from %s : %s' % \
                                            (self.host, self.port), 'net')
          self.state = CONNECTED
          self.api('core.events:raise:event')('client_connected', {'client':self},
                                              calledfrom="client")
          self.api('send:client')("%s - %s: Client Connected" % \
                                      (self.host, self.port))
        elif vpw and data == vpw:
          self.api('send:msg')('Successful view password from %s : %s' % \
                              (self.host, self.port), 'net')
          self.state = CONNECTED
          self.view_only = True
          self.addtooutbufferevent(
              {'original':self.api('core.colors:colorcode:to:ansicode')(
                  '%s%s@W: @GYou are connected in view mode@w' % (self.api('net.proxy:preamble:error:color:get')(),
                                                                  self.api('net.proxy:preamble:get')()))})
          self.api('core.events:raise:event')('client_connected_view',
                                              {'client':self}, calledfrom="client")
          self.api('send:client')(
              "%s - %s: Client Connected (View Mode)" % \
                  (self.host, self.port))
        else:
          self.bad_password_count += 1
          if self.bad_password_count == 5:
            self.addtooutbufferevent(
                {'original':self.api('core.colors:colorcode:to:ansicode')(
                    '%s%s@w: %sYou have been BANNED for 10 minutes:@w' % (self.api('net.proxy:preamble:error:color:get')(),
                                                                          self.api('net.proxy:preamble:get')(),
                                                                          self.api('net.proxy:preamble:error:color:get')())),
                 'dtype':'passwd'})
            self.api('send:msg')('%s has been banned.' % self.host, 'net')
            self.api('net.clients:banned:add')(self.host)
            self.handle_close()
          else:
            self.addtooutbufferevent(
                {'original':self.api('core.colors:colorcode:to:ansicode')(
                    '%s%s@w: %sPlease try again! Proxy Password:@w' % (self.api('net.proxy:preamble:error:color:get')(),
                                                                       self.api('net.proxy:preamble:get')(),
                                                                       self.api('net.proxy:preamble:error:color:get')())),
                 'dtype':'passwd'})

  def handle_close(self):
    """
    handle a close
    """
    self.api('send:client')("%s - %s: Client Disconnected" % \
                                (self.host, self.port))
    self.api('send:msg')("%s - %s: Client Disconnected" % \
                                (self.host, self.port), primary='net')
    self.api('core.events:raise:event')('client_disconnected', {'client':self}, calledfrom="client")
    self.api('core.events:unregister:from:event')('to_client_event', self.addtooutbufferevent)
    while self.outbuffer:
      self.handle_write()
    Telnet.handle_close(self)
