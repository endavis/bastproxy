"""
This plugin will show information about connections to the proxy
"""
import time
import argparse
import os
import stat
from plugins._baseplugin import BasePlugin

#these 5 are required
NAME = 'Proxy Interface'
SNAME = 'proxy'
PURPOSE = 'control the proxy'
AUTHOR = 'Bast'
VERSION = 1
PRIORITY = 35

# This keeps the plugin from being autoloaded if set to False
AUTOLOAD = True


class Plugin(BasePlugin):
  """
  a plugin to show connection information
  """
  def __init__(self, *args, **kwargs):
    """
    initialize the instance
    """
    BasePlugin.__init__(self, *args, **kwargs)

    self.api.get('dependency.add')('ssc')

  def load(self):
    """
    load the plugins
    """
    BasePlugin.load(self)

    self.api('setting.add')('mudhost', '', str,
                        'the hostname/ip of the mud')
    self.api('setting.add')('mudport', 0, int,
                        'the port of the mud')
    self.api('setting.add')('listenport', 9999, int,
                        'the port for the proxy to listen on')
    self.api('setting.add')('username', '', str,
                        'username')

    self.api.get('commands.add')('clients', self.cmd_clients,
                              shelp='list clients that are connected')

    self.api.get('commands.add')('disconnect', self.cmd_disconnect,
                              shelp='disconnect from the mud')

    self.api.get('commands.add')('connect', self.cmd_connect,
                              shelp='connect to the mud')

    self.api.get('commands.add')('shutdown', self.cmd_shutdown,
                              shelp='shutdown the proxy')

    self.api('events.register')('client_connected', self.client_connected)
    self.api('events.register')('mudconnect', self.sendusernameandpw)
    self.api('events.register')('var_net_listenport', self.listenportchange)

    ssc = self.api('ssc.baseclass')()
    self.apikey = ssc('proxypw', self, desc='Proxy Password',
                      default='defaultpass')
    self.apikey = ssc('proxypwview', self, desc='Proxy View Password',
                      default='defaultviewpass')
    self.apikey = ssc('mudpw', self, desc='Mud Password')


  def sendusernameandpw(self, args):
    """
    if username and password are set, then send them when the proxy
    connects to the mud
    """
    if self.api('setting.gets')('username') != '':
      self.api('send.mud')(self.api('setting.gets')('username'))
      pw = self.api('%s.mudpw' % self.sname)()
      if pw != '':
        self.api('send.mud')(pw)

  def cmd_clients(self, _):
    """
    @G%(name)s@w - @B%(cmdname)s@w
    List connections
      @CUsage@w: list
    """
    proxy = self.api.get('managers.getm')('proxy')
    clientformat = '%-6s %-17s %-7s %-17s %-s'
    tmsg = ['']
    if proxy:
      tmsg.append('Host: %s' % proxy.host)
      tmsg.append('Port: %s' % proxy.port)
      if proxy.connectedtime:
        tmsg.append('PROXY: connected for %s' %
                self.api.get('utils.timedeltatostring')(proxy.connectedtime,
                                            time.mktime(time.localtime())))
      else:
        tmsg.append('PROXY: disconnected')

      tmsg.append('')
      tmsg.append(clientformat % ('Type', 'Host', 'Port',
                                            'Client', 'Connected'))
      tmsg.append('@B' + 60 * '-')
      for i in proxy.clients:
        ttime = self.api.get('utils.timedeltatostring')(i.connectedtime,
                                          time.mktime(time.localtime()))

        tmsg.append(clientformat % ('Active', i.host[:17], i.port,
                                          i.ttype[:17], ttime))
      for i in proxy.vclients:
        ttime = self.api.get('utils.timedeltatostring')(i.connectedtime,
                                          time.mktime(time.localtime()))
        tmsg.append(clientformat % ('View', i.host[:17], i.port,
                                          i.ttype[:17], ttime))

    return True, tmsg

  def cmd_disconnect(self, _=None):
    """
    disconnect from the mud
    """
    proxy = self.api.get('managers.getm')('proxy')
    proxy.handle_close()

    return True, ['Attempted to close the connection to the mud']

  def cmd_connect(self, _=None):
    """
    disconnect from the mud
    """
    proxy = self.api.get('managers.getm')('proxy')
    if proxy.connected:
      return True, ['The proxy is currently connected']
    else:
      proxy.connectmud(self.api.get('setting.gets')('mudhost'),
                      self.api.get('setting.gets')('mudport'))

      return True, ['Connecting to the mud']

  def cmd_shutdown(self, args):
    """
    shutdown the proxy
    """
    proxy = self.api('managers.getm')('proxy')
    self.api('plugins.savestate')()
    self.api('send.client')('Shutting down bastproxy')
    proxy.shutdown()

  def client_connected(self, args):
    """
    check for mud settings
    """
    proxy = self.api.get('managers.getm')('proxy')
    tmsg = []
    divider = '@R------------------------------------------------@w'
    if not proxy.connected:
      if not self.api('setting.gets')('mudhost'):
        tmsg.append(divider)
        tmsg.append('Please set the mudhost through the net plugin.')
        tmsg.append('#bp.proxy.set mudhost "host"')
      if self.api('setting.gets')('mudport') == 0:
        tmsg.append(divider)
        tmsg.append('Please set the mudport through the net plugin.')
        tmsg.append('#bp.proxy.set mudport "port"')
      tmsg.append('Connect to the mud with "#bp.proxy.connect"')
    else:
      tmsg.append(divider)
      tmsg.append('@R#BP@W: @GThe proxy is already connected to the mud@w')
    if self.api('%s.proxypw' % self.sname)() == 'defaultpass':
      tmsg.append(divider)
      tmsg.append('The proxy password is still the default password.')
      tmsg.append('Please set the proxy password!')
      tmsg.append('#bp.%s.proxypw "This is a password"' % self.sname)
    if self.api('%s.proxypwview' % self.sname)() == 'defaultviewpass':
      tmsg.append(divider)
      tmsg.append('The proxy view password is still the default password.')
      tmsg.append('Please set the proxy view password!')
      tmsg.append('#bp.%s.proxypwview "This is a view password"' % self.sname)
    if tmsg[-1] != divider:
      tmsg.append(divider)
    if tmsg[0] != divider:
      tmsg.insert(0, divider)

    if tmsg:
      self.api('send.client')(tmsg)

    return True

  def listenportchange(self, args):
    """
    restart when the listen port changes
    """
    if not self.api.loading:
      self.api('proxy.restart')()

