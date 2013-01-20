
from libs.net.telnetlib import Telnet
from libs import exported
from libs.color import strip_ansi
from libs.net.options import optionMgr


class Proxy(Telnet):
  def __init__(self, host, port):
    Telnet.__init__(self, host, port)
    self.clients = []

    self.username = None
    self.password = None
    self.lastmsg = ''
    self.clients = []
    self.ttype = 'Server'
    exported.registerevent('to_mud_event', self.addtooutbuffer, 99)
    optionMgr.addtoserver(self)

  def handle_read(self):
    Telnet.handle_read(self)

    data = self.getdata()
    if data:
      newdata = exported.processevent('net_read_data_filter',  {'data':data})
      self.msg('newdata', newdata)
      if 'adjdata' in newdata:
        data = newdata['adjdata']

      ndata = self.lastmsg + data
      alldata = ndata.replace("\r","")
      ndatal = alldata.split('\n')
      self.lastmsg = ndatal[-1]
      for i in ndatal[:-1]:
        exported.processevent('to_user_event', {'todata':i, 'dtype':'frommud', 'noansidata':strip_ansi(i)})

  def addclient(self, client):
    self.clients.append(client)

  def connectmud(self):
    exported.debug('connectmud')
    self.doconnect()
    exported.processevent('mudconnect', {})

  def handle_close(self):
    exported.debug('Server Disconnected')
    exported.processevent('to_user_event', {'todata':'The mud closed the connection', 'dtype':'fromproxy'})
    optionMgr.resetoptions(self, True)
    Telnet.handle_close(self)
    exported.processevent('muddisconnect', {})  

  def removeclient(self, client):
    if client in self.clients:
      self.clients.remove(client)

  def addtooutbuffer(self, args, raw=False):
    data = ''
    if isinstance(args, dict):
      data = args['data']
      if 'raw' in args:
        raw = args['raw']
    else:
      data = args

    Telnet.addtooutbuffer(self, data, raw)
