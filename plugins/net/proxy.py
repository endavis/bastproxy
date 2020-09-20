"""
This plugin will show information about connections to the proxy
"""
import time
import os
import sys
import platform
from plugins._baseplugin import BasePlugin

#these 5 are required
NAME = 'Proxy Interface'
SNAME = 'proxy'
PURPOSE = 'control the proxy'
AUTHOR = 'Bast'
VERSION = 1
PRIORITY = 35

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

    self.api('dependency:add')('core.ssc')

    self.proxypw = None
    self.proxyvpw = None
    self.mudpw = None

    # new api format
    self.api('api:add')('proxy:restart', self.api_restart)
    self.api('api:add')('proxy:shutdown', self.api_shutdown)
    self.api('api:add')('preamble:get', self.api_preamble)
    self.api('api:add')('preamble:color:get', self.api_preamble_color)
    self.api('api:add')('preamble:error:color:get', self.api_preamble_error_color)

  def initialize(self):
    """
    initialize the plugin
    """
    BasePlugin.initialize(self)

    self.api('setting:add')('mudhost', '', str,
                            'the hostname/ip of the mud')
    self.api('setting:add')('mudport', 0, int,
                            'the port of the mud')
    self.api('setting:add')('listenport', 9999, int,
                            'the port for the proxy to listen on')
    self.api('setting:add')('username', '', str,
                            'username')
    self.api('setting:add')('linelen', 79, int,
                            'the line length for data')
    self.api('setting:add')('preamble', '#BP', str,
                            'the preamble from any proxy output')
    self.api('setting:add')('preamblecolor', '@C', str,
                            'the preamble color')
    self.api('setting:add')('preambleerrorcolor', '@R', str,
                            'the preamble color for an error line')
    self.api('setting:add')('cmdseperator', '|', str,
                            'the seperator for sending multiple commands')

    self.api('core.commands:command:add')('info',
                                          self.cmd_info,
                                          shelp='list proxy info')

    self.api('core.commands:command:add')('disconnect',
                                          self.cmd_disconnect,
                                          shelp='disconnect from the mud')

    self.api('core.commands:command:add')('connect',
                                          self.cmd_connect,
                                          shelp='connect to the mud')

    self.api('core.commands:command:add')('restart',
                                          self.cmd_restart,
                                          shelp='restart the proxy',
                                          format=False)

    self.api('core.commands:command:add')('shutdown',
                                          self.cmd_shutdown,
                                          shelp='shutdown the proxy')

    self.api('core.events:register:to:event')('client_connected', self.client_connected)
    self.api('core.events:register:to:event')('mudconnect', self.sendusernameandpw)
    self.api('core.events:register:to:event')('%s_var_%s_modified' % (self.plugin_id, 'listenport'),
                                              self.listen_port_change)
    self.api('core.events:register:to:event')('%s_var_%s_modified' % (self.plugin_id, 'cmdseparator'),
                                              self.command_seperator_change)

    ssc = self.api('core.ssc:baseclass:get')()
    self.proxypw = ssc('proxypw', self, desc='Proxy Password',
                       default='defaultpass')
    self.proxyvpw = ssc('proxypwview', self, desc='Proxy View Password',
                        default='defaultviewpass')
    self.mudpw = ssc('mudpw', self, desc='Mud Password')

  def api_preamble(self):
    """
    get the preamble
    """
    return self.api('setting:get')('preamble')

  def api_preamble_color(self):
    """
    get the preamble
    """
    return self.api('setting:get')('preamblecolor')

  def api_preamble_error_color(self):
    """
    get the preamble
    """
    return self.api('setting:get')('preambleerrorcolor')

  def sendusernameandpw(self, args): # pylint: disable=unused-argument
    """
    if username and password are set, then send them when the proxy
    connects to the mud
    """
    if self.api('setting:get')('username') != '':
      self.api('send:mud')(self.api('setting:get')('username'))
      pasw = self.api('%s:ssc:mudpw' % self.plugin_id)()
      if pasw != '':
        self.api('send:mud')(pasw)
      self.api('send:mud')('\n')
      self.api('send:mud')('\n')

  def cmd_info(self, _):
    """
    show info about the proxy
    """
    template = "%-15s : %s"
    mud = self.api('managers:get')('mud')
    tmsg = ['']
    started = time.strftime(self.api.time_format, self.api.proxy_start_time)
    uptime = self.api('core.utils:convert:timedelta:to:string')(
        self.api.proxy_start_time,
        time.localtime())

    tmsg.append('@B-------------------  Proxy ------------------@w')
    tmsg.append(template % ('Started', started))
    tmsg.append(template % ('Uptime', uptime))
    tmsg.append(template % ('Python Version', platform.python_version()))
    tmsg.append('')
    tmsg.append('@B-------------------   Mud  ------------------@w')
    if mud:
      if mud.connected_time:
        tmsg.append(template % ('Connected',
                                time.strftime(self.api.time_format,
                                              mud.connected_time)))
        tmsg.append(template % ('Uptime', self.api('core.utils:convert:timedelta:to:string')(
            mud.connected_time,
            time.localtime())))
        tmsg.append(template % ('Host', mud.host))
        tmsg.append(template % ('Port', mud.port))
      else:
        tmsg.append(template % ('Mud', 'disconnected'))

    clients = self.api('net.clients:clients:get:all')()

    aclients = clients['active']
    vclients = clients['view']

    tmsg.append('')
    tmsg.append('@B-----------------   Clients  ----------------@w')
    tmsg.append(template % ('Clients', len(aclients)))
    tmsg.append(template % ('View Clients', len(vclients)))
    tmsg.append('-------------------------')

    _, nmsg = self.api('core.commands:command:run')('clients', 'show', '')

    del nmsg[0]
    del nmsg[0]
    tmsg.extend(nmsg)
    return True, tmsg

  def cmd_disconnect(self, args=None): # pylint: disable=unused-argument
    """
    disconnect from the mud
    """
    mud = self.api('managers:get')('mud')
    if mud.connected:
      mud.handle_close()

      return True, ['Attempted to close the connection to the mud']
    else:
      return True, ['The proxy is not connected to the mud']

  def cmd_connect(self, args=None): # pylint: disable=unused-argument
    """
    disconnect from the mud
    """
    mud = self.api('managers:get')('mud')
    if mud.connected:
      return True, ['The proxy is currently connected to the mud']

    mud.connectmud(self.api('setting:get')('mudhost'),
                   self.api('setting:get')('mudport'))

    return True, ['Connecting to the mud']

  def api_shutdown(self):
    """
    shutdown the proxy
    """
    self.api.__class__.shutdown = True
    self.api('send:msg')('Proxy: shutdown started', secondary='shutdown')
    self.api('send:client')('Shutting down bastproxy')
    self.api('core.events:raise:event')('proxy_shutdown')
    self.api('send:msg')('Proxy: shutdown finished', secondary='shutdown')

  def cmd_shutdown(self, args=None): # pylint: disable=unused-argument,no-self-use
    """
    shutdown the proxy
    """
    raise KeyboardInterrupt

  def cmd_restart(self, args): # pylint: disable=unused-argument
    """
    restart the proxy
    """
    self.api('net.proxy:proxy:restart')()

  def client_connected(self, args): # pylint: disable=unused-argument
    """
    check for mud settings
    """
    mud = self.api('managers:get')('mud')
    cmdprefix = self.api('core.commands:get:command:prefix')()
    tmsg = []
    divider = '@R------------------------------------------------@w'
    if not mud.connected:
      if not self.api('setting:get')('mudhost'):
        tmsg.append(divider)
        tmsg.append('Please set the mudhost through the net plugin.')
        tmsg.append('%s.%s.set mudhost "host"' % (cmdprefix, self.plugin_id))
      if self.api('setting:get')('mudport') == 0:
        tmsg.append(divider)
        tmsg.append('Please set the mudport through the net plugin.')
        tmsg.append('%s.%s.set mudport "port"' % (cmdprefix, self.plugin_id))
      tmsg.append('Connect to the mud with "%s.%s.connect"' % (cmdprefix, self.plugin_id))
    else:
      tmsg.append(divider)
      tmsg.append('%s%s@W: @GThe proxy is already connected to the mud@w' % \
                    (self.api('net.proxy:preamble:error:color:get')(), self.api('net.proxy:preamble:get')()))
    if self.api('%s:ssc:proxypw' % self.plugin_id)() == 'defaultpass':
      tmsg.append(divider)
      tmsg.append('The proxy password is still the default password.')
      tmsg.append('Please set the proxy password!')
      tmsg.append('%s.%s.proxypw "This is a password"' % (cmdprefix, self.plugin_id))
    if self.api('%s:ssc:proxypwview' % self.plugin_id)() == 'defaultviewpass':
      tmsg.append(divider)
      tmsg.append('The proxy view password is still the default password.')
      tmsg.append('Please set the proxy view password!')
      tmsg.append('%s.%s.proxypwview "This is a view password"' % (cmdprefix, self.plugin_id))
    if tmsg[-1] != divider:
      tmsg.append(divider)
    if tmsg[0] != divider:
      tmsg.insert(0, divider)

    if tmsg:
      self.api('send:client')(tmsg, client=args['client'])

    return True

  # restart the proxy
  def api_restart(self):
    """
    restart the proxy after 10 seconds
    """
    listen_port = self.api('setting:get')('listenport')

    self.api('send:client')("Respawning bastproxy on port: %s in 10 seconds" \
                                              % listen_port)

    self.api('core.timers:add:timer')('restart', self.timer_restart, 5, onetime=True)

  def timer_restart(self):
    """
    a function to restart the proxy after a timer
    """
    self.api('core.plugins:save:state')()

    executable = sys.executable
    args = []
    args.insert(0, 'bastproxy.py')
    args.insert(0, sys.executable)

    plistener = self.api('managers:get')('listener')
    plistener.close()
    self.api('net.proxy:proxy:shutdown')()

    time.sleep(5)

    os.execv(executable, args)

  def listen_port_change(self, args): # pylint: disable=unused-argument
    """
    restart when the listen port changes
    """
    if not self.api.startup:
      self.api('net.proxy:proxy:restart')()

  def command_seperator_change(self, args): # pylint: disable=unused-argument
    """
    update the command regex
    """
    newsep = args['newvalue']

    self.api.__class__.command_split_regex = r'(?<=[^%s])%s(?=[^%s])' % ('\\' + newsep, '\\' + newsep, '\\' + newsep)
