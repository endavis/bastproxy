#!/usr/bin/env python
"""
## About
This is a mud proxy.
It runs in python 2.X (>2.6).

It supports MCCP, GMCP, aliases, actions, substitutes, variables
## Installation
### Git
 * ```git clone https://github.com/endavis/bastproxy.git```

### Download
 * Download the zip file from
      [here](https://github.com/endavis/bastproxy/archive/master.zip).
 * Unzip into a directory

## Getting Started

### Starting
 * From the installation directory, ```python bastproxy.py```

```
usage: bastproxy.py [-h] [-p PORT] [-d]

A python mud proxy

optional arguments:
  -h, --help            show this help message and exit
  -p PORT, --port PORT  the port for the proxy to listen on
  -d, --daemon          run in daemon mode
```

### Connecting
  * Connect a client to the listen_port above on the host the proxy is running,
      and then login with the password
   * Default Port: 9999
     * to set a different port after logging in ```#bp.proxy.set listenport portnum```
   * Default Password: "defaultpass"
     * to set a different password after loggin in ```#bp.proxy.proxypw "new password"```
   * Setting up the mud to connect to
     * to set the mud server ```#bp.proxy.set mudhost some.server```
     * to set the mud port ```#bp.proxy.set mudport portnum```
   * Setting up autologin
     * to set the user ```#bp.proxy.set username user```
     * to set the password ```#bp.proxy.mudpw password```
   * Connecting to the mud
     * ```#bp.proxy.connect```

### Help
  * Use the following commands to get help
   * Show command categories
     * ```#bp.commands```
   * show commands in a category
     * ```#bp.commands.list "category"```
     * ```#bp."category"```
   * Show loaded plugins
     * ```#bp.plugins```
   * Show plugins that are not loaded
     * ```#bp.plugins -n```

## Basics
### Plugins
  * Plugins are the basic building block for bastproxy, and are used through
  the commands that are added by the plugin.

### Commands
#### Help
  * Any command will show a help when adding a -h

#### Arguments
  * command line arguments are parsed like a unix shell command line
  * to specify an argument with spaces, surround it with double 's or "s
   * Examples:
    * ```#bp.plugins.cmd first second```
     * 1st argument = 'first'
     * 2nd argument = 'second'
    * ```#bp.plugins.cmd 'this is the first argument'
              "this is the second argument"```
     * 1st argument = 'this is the first argument'
     * 2nd argument = 'this is the second argument'
"""
import asyncore
import os
import sys
import socket
import time
from libs.api import API as BASEAPI
import libs.argp as argp
# import libs.timing so that the timing functions are added to the api
import libs.timing      # pylint: disable=unused-import
# import io so the "send" functions are added to the api
from libs import io      # pylint: disable=unused-import

sys.stderr = sys.stdout

VERSION = "2.0.0"

# create and API instance and update start time and set the startup flag
API = BASEAPI()
BASEAPI.proxy_start_time = time.localtime()
BASEAPI.startup = True

def setup_paths():
  """
  find the base path of the bastproxy.py file for later use
  in importing plugins and create data directories
  """
  npath = os.path.abspath(__file__)
  index = npath.rfind(os.sep)
  tpath = ''
  if index == -1:
    tpath = os.curdir + os.sep
  else:
    tpath = npath[:index]

  API('send.msg')('setting basepath to: %s' % tpath, 'startup')
  BASEAPI.BASEPATH = tpath

  # create the logs directory
  try:
    os.makedirs(os.path.join(API.BASEPATH, 'data', 'logs'))
  except OSError:
    pass


class Listener(asyncore.dispatcher):
  """
  This is the class that listens for new clients
  """
  def __init__(self, listen_port):
    """
    init the class

    arguments:
      required:
        listen_port - the port to listen on
    """
    # setup asyncore
    asyncore.dispatcher.__init__(self)
    self.create_socket(socket.AF_INET, socket.SOCK_STREAM)
    self.set_reuse_addr()
    self.bind(("", listen_port))
    self.listen(50)

    # set the mud to None, it is created later
    self.mud = None

    # create a list of clients
    self.clients = []
    API('send.msg')("Listener bound on: %s" % listen_port, 'startup')

  def handle_error(self):
    """
    show the traceback for an error in the listener
    """
    API('send.traceback')("Forwarder error:")

  def handle_accept(self):
    """
    accept a new client
    """

    # create a connection to the mud if it doesn't exist
    if not self.mud:
      from libs.net.mud import Mud

      # do proxy stuff here
      self.mud = Mud()

    # accept the new connection
    client_connection, source_addr = self.accept()

    try:
      # if the client is banned, close the connection
      ip_address = source_addr[0]
      if API('clients.checkbanned')(ip_address):
        API('send.msg')("HOST: %s is banned" % ip_address, 'net')
        client_connection.close()
      # if there are more than 5 connections, close the current connection
      elif API('clients.numconnected') == 5:
        API('send.msg')(
            "Only 5 clients can be connected at the same time", 'net')
        client_connection.close()
      else:
        API('send.msg')("Accepted connection from %s : %s" %
                        (source_addr[0], source_addr[1]), 'net')

        # create a Client instance
        from libs.net.client import Client
        Client(client_connection, source_addr[0], source_addr[1])

    # catch everything because we don't want to exit if we can't connect a
    # client
    except Exception:   # pylint: disable=broad-except
      API('send.traceback')('Error handling client')

def start(listen_port):
  """
  start the proxy

  we do a single asyncore.loop of .25 seconds, then we check timers

  arguments:
    required:
      listen_port - the port to listen on
  """
  API('managers.add')('listener', Listener(listen_port))

  try:
    while True:

      asyncore.loop(timeout=.25, count=1)

      if API.shutdown:
        break

      # check our timer event
      API('events.eraise')('global_timer', {}, calledfrom="globaltimer")

  # catch a KeyBoardInterrupt so that bastproxy can be exited
  except KeyboardInterrupt:
    pass

  API('send.msg')("asyncore loop broken", primary='net')


def main():
  """
  the main function that runs everything
  """
  setup_paths()

  # create an ArgumentParser to parse the command line
  parser = argp.ArgumentParser(description='A python mud proxy')
  # create a port option, this sets the variable automatically in the proxy plugin
  parser.add_argument('-p', "--port",
                      help="the port for the proxy to listen on",
                      default=9999)
  # create a daemon option, which puts the proxy into daemon mode
  parser.add_argument('-d', "--daemon",
                      help="run in daemon mode",
                      action='store_true')
  targs = vars(parser.parse_args())

  daemon = bool(targs['daemon'])

  # initialize all plugins
  API('send.msg')('Plugin Manager - loading', 'startup')
  # instantiate the plugin manager
  from plugins import PluginMgr
  plugin_manager = PluginMgr()

  # initialize the plugin manager which will load plugins
  plugin_manager.initialize()
  API('send.msg')('Plugin Manager - loaded', 'startup')

  # add some logging of various plugins and functionality
  API('log.adddtype')('net')
  API('log.console')('net')
  API('log.adddtype')('inputparse')
  API('log.adddtype')('ansi')

  # get the proxy plugin
  proxy_plugin = API('core.plugins:get:plugin:instance')('proxy')

  # update the port setting if different from the default
  if targs['port'] != 9999:
    proxy_plugin.api('setting:change')('listenport', targs['port'])

  # get the listen port setting
  listen_port = proxy_plugin.api('setting:gets')('listenport')

  # the proxy is done starting up and we raise an event
  BASEAPI.startup = False
  API('events.eraise')('proxy_ready', calledfrom='bastproxy')

  # start the proxy in an infinite loop which can be broken with a Ctrl-C
  if not daemon:
    # start without daemon mode
    try:
      start(listen_port)
    except KeyboardInterrupt:
      pass

    API('proxy.shutdown')()

  else:
    # start with daemon mode
    os.close(0)
    os.close(1)
    os.close(2)
    os.open("/dev/null", os.O_RDONLY)
    os.open("/dev/null", os.O_RDWR)
    os.dup(1)

    # fork the proxy for daemon mode
    if os.fork() == 0:
      # We are the child
      try:
        sys.exit(start(listen_port))
      except KeyboardInterrupt:
        pass
      sys.exit(0)

  API('send.msg')("exiting main function", primary='net')

if __name__ == "__main__":
  main()
