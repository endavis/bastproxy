"""
This file holds the class that connects to the mud
"""
import time
from libs.net.telnetlib import Telnet
from libs.api import API


class Proxy(Telnet):
  """
  This class is for the proxy that connects to the mud
  """
  def __init__(self):
    """
    init the class
    """
    Telnet.__init__(self)

    self.username = None
    self.password = None
    self.api = API()
    self.lastmsg = ''
    self.clients = []
    self.vclients = []
    self.ttype = 'BastProxy'
    self.banned = {}
    self.connectedtime = None
    self.api('events.register')('to_mud_event', self.addtooutbuffer,
                                prio=99)
    self.api('options.prepareserver')(self)
    self.api('managers.add')('proxy', self)

  def handle_read(self):
    """
    handle a read
    """
    Telnet.handle_read(self)

    data = self.getdata()
    if data:
      ndata = "".join([self.lastmsg, data])
      alldata = ndata.replace("\r", "")
      ndatal = alldata.split('\n')
      self.lastmsg = ndatal[-1]
      for i in ndatal[:-1]:
        tosend = i
        try:
          tnoansi = self.api('colors.stripansi')(tosend)
        except AttributeError:
          tnoansi = tosend
        try:
          tconvertansi = self.api('colors.convertansi')(tosend)
        except AttributeError:
          tconvertansi = tosend
        if tosend != tconvertansi:
          self.api('send.msg')('converted %s to %s' % (repr(tosend),
                                                       tconvertansi),
                               'ansi')
        newdata = self.api('events.eraise')('from_mud_event',
                                            {'original':tosend,
                                             'dtype':'frommud',
                                             'noansi':tnoansi,
                                             'convertansi':tconvertansi})

        if 'original' in newdata:
          tosend = newdata['original']

        if 'omit' in newdata and newdata['omit']:
          tosend = None

        if tosend != None:
          #data cannot be transformed here
          if self.api('api.has')('colors.stripansi'):
            tnoansi = self.api('colors.stripansi')(tosend)
          else:
            tnoansi = tosend
          if self.api('api.has')('colors.convertansi'):
            tconvertansi = self.api('colors.convertansi')(tosend)
          else:
            tconvertansi = tosend
          self.api('events.eraise')('to_client_event',
                                    {'original':tosend,
                                     'dtype':'frommud',
                                     'noansi':tnoansi,
                                     'convertansi':tconvertansi})

  def addclient(self, client):
    """
    add a client

    required:
      client - the client to add
    """
    if client.viewonly:
      self.vclients.append(client)
    else:
      self.clients.append(client)

  def removeclient(self, client):
    """
    remove a client

    required:
      client - the client to remove
    """
    if client in self.clients:
      self.clients.remove(client)
    elif client in self.vclients:
      self.vclients.remove(client)

  def addbanned(self, clientip):
    """
    add a banned client

    required
      clientip - the client ip to ban
    """
    self.banned[clientip] = time.time()

  def checkbanned(self, clientip):
    """
    check if a client is banned

    required
      clientip - the client ip to check
    """
    if clientip in self.banned:
      return True
    return False

  def connectmud(self, mudhost, mudport):
    """
    connect to the mud
    """
    if self.connected:
      return
    self.outbuffer = ''
    self.doconnect(mudhost, mudport)
    self.connectedtime = time.localtime()
    self.api('send.msg')('Connected to mud', 'net')
    self.api('events.eraise')('mudconnect', {})

  def handle_close(self):
    """
    hand closing the connection
    """
    self.api('send.msg')('Disconnected from mud', 'net')
    self.api('events.eraise')('to_client_event',
                              {'original':self.api('colors.convertcolors')(
                                  '@R#BP@w: The mud closed the connection'),
                               'dtype':'fromproxy'})
    self.api('options.resetoptions')(self, True)
    Telnet.handle_close(self)
    self.connectedtime = None
    self.api('events.eraise')('muddisconnect', {})

  def addtooutbuffer(self, data, raw=False):
    """
    add to the outbuffer

    required:
      data - a string
             or a dictionary that contains a data key and a raw key

    optional:
      raw - set a raw flag, which means IAC will not be doubled
    """
    dtype = 'fromclient'
    datastr = ""
    trace = None
    if isinstance(data, dict):
      datastr = data['data']
      dtype = data['dtype']
      if 'raw' in data:
        raw = data['raw']
      if 'trace' in data:
        trace = data['trace']
    else:
      datastr = data

    if len(dtype) == 1 and ord(dtype) in self.options:
      if trace:
        trace['changes'].append({'flag':'Sent',
                                 'data':'"%s" to mud with raw: %s and datatype: %s' %
                                        (repr(datastr.strip()), raw, dtype),
                                 'plugin':'proxy'})
      Telnet.addtooutbuffer(self, datastr, raw)
    elif dtype == 'fromclient':
      if trace:
        trace['changes'].append({'flag':'Sent',
                                 'data':'"%s" to mud with raw: %s and datatype: %s' %
                                        (datastr.strip(), raw, dtype),
                                 'plugin':'proxy'})
      Telnet.addtooutbuffer(self, datastr, raw)

  def shutdown(self):
    """
    shutdown the proxy
    """
    API.shutdown = True
    self.api('send.msg')('Proxy: shutdown started', primary='net')
    self.api('events.eraise')('shutdown', {})
    for client in self.clients:
      client.handle_close()
    self.api('send.msg')('Proxy: shutdown finished', primary='net')
