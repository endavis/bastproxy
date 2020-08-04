"""
This plugin will show information about connections to the proxy
"""
import time
from plugins._baseplugin import BasePlugin

#these 5 are required
NAME = 'Clients'
SNAME = 'clients'
PURPOSE = 'manage clients'
AUTHOR = 'Bast'
VERSION = 1
PRIORITY = 35

# This keeps the plugin from being autoloaded if set to False
REQUIRED = True

class Plugin(BasePlugin):
  """
  a plugin to show connection information
  """
  def __init__(self, *args, **kwargs):
    """
    initialize the instance
    """
    BasePlugin.__init__(self, *args, **kwargs)

    self.can_reload_f = False

    self.clients = []
    self.vclients = []
    self.banned = {}

    self.api('api.add')('getall', self.api_getall)
    self.api('api.add')('addbanned', self.api_addbanned)
    self.api('api.add')('checkbanned', self.api_checkbanned)
    self.api('api.add')('numconnected', self.api_numconnected)

  def initialize(self):
    """
    initialize the plugin
    """
    BasePlugin.initialize(self)

    self.api('commands.add')('show',
                             self.cmd_show,
                             shelp='list clients that are connected')

    self.api('events.register')('proxy_shutdown',
                                self.shutdown)

    self.api('events.register')('client_connected', self.addclient)
    self.api('events.register')('client_connected_view', self.addviewclient)

    self.api('events.register')('client_disconnected', self.removeclient)

  def api_numconnected(self):
    """
    return the # of clients connected
    """
    return len(self.clients)

  def api_addbanned(self, clientip):
    """
    add a banned ip
    """
    self.banned[clientip] = time.time()

  def api_checkbanned(self, clientip):
    """
    check if a client is banned

    required
      clientip - the client ip to check
    """
    if clientip in self.banned:
      return True
    return False

  def addclient(self, args):
    """
    add a client from the connected event
    """
    self.clients.append(args['client'])

  def addviewclient(self, args):
    """
    add a view client from the connected event
    """
    self.vclients.append(args['client'])

  def removeclient(self, args):
    """
    remove a client
    """
    client = args['client']
    if client in self.clients:
      del self.clients[self.clients.index(client)]
    if client in self.vclients:
      del self.vclients[self.vclients.index(client)]

  def shutdown(self, args=None): # pylint: disable=unused-argument
    """
    close all clients
    """
    for client in self.clients:
      client.handle_close()
    for client in self.vclients:
      client.handle_close()

  def api_getall(self):
    """
    return a dictionary of clients
    two keys: view, active
    """
    return {'view':self.vclients, 'active':self.clients}

  def cmd_show(self, args): # pylint: disable=unused-argument
    """
    show all clients
    """
    clientformat = '%-6s %-17s %-7s %-17s %-s'
    tmsg = ['']
    tmsg.append(clientformat % ('Type', 'Host', 'Port',
                                'Client', 'Connected'))
    tmsg.append('@B' + 60 * '-')
    for i in self.clients:
      ttime = self.api('utils.timedeltatostring')(
          i.connectedtime,
          time.localtime())

      tmsg.append(clientformat % ('Active', i.host[:17], i.port,
                                  i.ttype[:17], ttime))
    for i in self.vclients:
      ttime = self.api('utils.timedeltatostring')(
          i.connectedtime,
          time.localtime())
      tmsg.append(clientformat % ('View', i.host[:17], i.port,
                                  i.ttype[:17], ttime))

    return True, tmsg
