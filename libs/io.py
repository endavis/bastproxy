"""
handle output and input functions, adds items under the send api
"""
from __future__ import print_function
import time
import sys
import traceback
import re
from libs.api import API

class ProxyIO(object):  # pylint: disable=too-few-public-methods
  """
  class for IO in the proxy
    APIs for this class
     'send:msg'       : send data through the messaging system for
                          logging purposes
     'send:error'     : send an error
     'send:traceback' : send a traceback
     'send:client'    : send data to the clients
     'send:mud'       : send data to the mud
     'send:execute'   : send data through the parser
  """
  def __init__(self):
    """
    initialize the class
    """
    self.current_trace = None
    self.api = API()

    self.api('libs.api:add')('libs.io', 'send:msg', self._api_msg)
    self.api('libs.api:add')('libs.io', 'send:error', self._api_error)
    self.api('libs.api:add')('libs.io', 'send:traceback', self._api_traceback)
    self.api('libs.api:add')('libs.io', 'send:client', self._api_client)
    self.api('libs.api:add')('libs.io', 'send:mud', self._api_tomud)
    self.api('libs.api:add')('libs.io', 'send:execute', self._api_execute)

  # send a message
  def _api_msg(self, message, primary=None, secondary=None):
    """  send a message through the log plugin
      @Ymessage@w        = This message to send
      @Yprimary@w    = the primary data tag of the message (default: None)
      @Ysecondary@w  = the secondary data tag of the message
                          (default: None)

    If a plugin called this function, it will be automatically added to the tags

    this function returns no values"""
    tags = []
    plugin = self.api('libs.api:get:caller:plugin')(ignore_plugin_list=['core.plugins'])

    tags.extend(self.api('libs.api:get:plugins:from:stack:list')(ignore_plugin_list=['core.plugins']))

    if not isinstance(secondary, list):
      tags.append(secondary)
    else:
      tags.extend(secondary)

    ttags = set(tags) # take out duplicates
    tags = list(ttags)

    if primary:
      if primary in tags:
        tags.remove(primary)
      tags.insert(0, primary)

    if plugin:
      if not primary:
        if plugin in tags:
          tags.remove(plugin)
        tags.insert(0, plugin)
      else:
        if plugin not in tags:
          tags.append(plugin)

    if not tags:
      print('Did not get any tags for %s' % message)

    try:
      self.api('core.log:message')(message, tags=tags)
    except (AttributeError, RuntimeError): #%s - %-10s :
      print('%s - %-15s : %s' % (time.strftime(self.api.time_format,
                                               time.localtime()),
                                 primary or plugin, message))

  # write and format a traceback
  def _api_traceback(self, message=""):
    """  handle a traceback
      @Ymessage@w  = the message to put into the traceback

    this function returns no values"""
    exc = "".join(traceback.format_exception(sys.exc_info()[0],
                                             sys.exc_info()[1],
                                             sys.exc_info()[2]))

    if message:
      message = "".join([message, "\n", exc])
    else:
      message = exc

    self.api('send:error')(message)

  # write and format an error
  def _api_error(self, text, secondary=None):
    """  handle an error
      @Ytext@w      = The error to handle
      @Ysecondary@w = Other datatypes to flag this data

    this function returns no values"""
    text = str(text)
    message_list = []

    for i in text.split('\n'):
      if self.api('libs.api:has')('core.colors:colorcode:to:ansicode'):
        message_list.append('@x136%s@w' % i)
      else:
        message_list.append(i)
    message = '\n'.join(message_list)

    self.api('send:msg')(message, primary='error', secondary=secondary)

    try:
      self.api('core.errors:add')(time.strftime(self.api.time_format,
                                                time.localtime()),
                                  message)
    except (AttributeError, TypeError):
      pass

  # send text to the clients
  def _api_client(self, text, raw=False, preamble=True, dtype='fromproxy', client=None):  # pylint: disable=too-many-arguments
    """  handle a traceback
      @Ytext@w      = The text to send to the clients
      @Yraw@w       = if True, don't convert colors or add the preamble
      @Ypreamble@w  = if True, send the preamble, defaults to True
      @Ydtype@w     = datatype, defaults to "fromproxy"

    this function returns no values"""

    # if the data is from the proxy (internal) and not raw, add the preamble to each line
    if not raw and dtype == 'fromproxy':
      if isinstance(text, basestring):
        text = text.split('\n')

      test = []
      for i in text:
        if preamble:
          i = "".join(['%s%s@w: ' % (self.api('net.proxy:preamble:color:get')(),
                                     self.api('net.proxy:preamble:get')()), i])
        if self.api('libs.api:has')('core.colors:colorcode:to:ansicode'):
          test.append(self.api('core.colors:colorcode:to:ansicode')(i))
        else:
          test.append(i)
      text = test
      text = "\n".join(text)

    try:
      self.api('core.events:raise:event')('to_client_event', {'original':text,
                                                              'raw':raw, 'dtype':dtype,
                                                              'client':client},
                                          calledfrom="io")
    except (NameError, TypeError, AttributeError):
      self.api('send:traceback')("couldn't send msg to client: %s" % text)

  # execute a command through the interpreter, most data goes through this
  def _api_execute(self, command, fromclient=False, showinhistory=True): # pylint: disable=too-many-branches
    """  execute a command through the interpreter
    It will first check to see if it is an internal command, and then
    send to the mud if not.
      @Ycommand@w      = the command to send through the interpreter

    this function returns no values"""
    self.api('send:msg')('execute: got command %s' % repr(command),
                         primary='inputparse')

    new_trace = False
    if not self.current_trace:
      new_trace = True
      self.current_trace = {}
      self.current_trace['fromclient'] = False
      self.current_trace['internal'] = True
      self.current_trace['changes'] = []
      self.current_trace['showinhistory'] = showinhistory
      self.current_trace['addedtohistory'] = False
      self.current_trace['originalcommand'] = command.strip()
      self.current_trace['fromplugin'] = self.api('libs.api:get:caller:plugin')()

      if fromclient:
        self.current_trace['fromclient'] = True
        self.current_trace['internal'] = False

      self.api('core.events:raise:event')('io_execute_trace_started', self.current_trace,
                                          calledfrom="io")

    if command == '\r\n':
      self.api('send:msg')('sending %s (cr) to the mud' % repr(command),
                           primary='inputparse')
      self.api('core.events:raise:event')('to_mud_event', {'data':command,
                                                           'dtype':'fromclient',
                                                           'showinhistory':showinhistory,
                                                           'trace':self.current_trace},
                                          calledfrom="io")
    else:

      command = command.strip()

      commands = command.split('\r\n')
      if len(commands) > 1:
        self.current_trace['changes'].append({'flag':'Splitcr',
                                              'data':'split command: "%s" into: "%s"' % \
                                                         (command, ", ".join(commands)),
                                              'plugin':'io'})

      for current_command in commands:
        newdata = self.api('core.events:raise:event')('io_execute_event',
                                                      {'fromdata':current_command,
                                                       'fromclient':fromclient,
                                                       'internal':not fromclient,
                                                       'showinhistory':showinhistory,
                                                       'trace':self.current_trace},
                                                      calledfrom="io")

        if 'fromdata' in newdata:
          current_command = newdata['fromdata']
          current_command = current_command.strip()

        if current_command:
          # split the command if it has the command seperator in it
          # and run each one through execute again
          if self.api.command_split_regex:
            split_data = re.split(self.api.command_split_regex, current_command)
          else:
            split_data = []
          if len(split_data) > 1:
            self.api('send:msg')('broke %s into %s' % (current_command, split_data),
                                 primary='inputparse')
            self.current_trace['changes'].append(
                {'flag':'Splitchar',
                 'data':'split command: "%s" into: "%s"' % \
                   (current_command, ", ".join(split_data)),
                 'plugin':'io'})
            for cmd in split_data:
              self.api('send:execute')(cmd, showinhistory=showinhistory)

          # the command did not have a command seperator
          else:
            # take out double command seperators and replaces them with a single one before
            # sending the data to the mud
            current_command = current_command.replace('||', '|')
            if current_command[-1] != '\n':
              current_command = "".join([current_command, '\n'])
            self.api('send:msg')('sending %s to the mud' % current_command.strip(),
                                 primary='inputparse')
            self.api('core.events:raise:event')('to_mud_event',
                                                {'data':current_command,
                                                 'dtype':'fromclient',
                                                 'showinhistory':showinhistory,
                                                 'trace':self.current_trace},
                                                calledfrom="io")

    if new_trace:
      self.api('core.events:raise:event')('io_execute_trace_finished', self.current_trace,
                                          calledfrom="io")
      self.current_trace = None

  # send data directly to the mud
  def _api_tomud(self, data, raw=False, dtype='fromclient'):
    """ send data directly to the mud

    This does not go through the interpreter
      @Ydata@w     = the data to send
      @Yraw@w      = don't do anything to this data
      @Ydtype@w    = the datatype

    this function returns no values
    """

    if not raw and data and data[-1] != '\n':
      data = "".join([data, '\n'])
    self.api('core.events:raise:event')('to_mud_event',
                                        {'data':data,
                                         'dtype':dtype,
                                         'raw':raw},
                                        calledfrom="io")

IO = ProxyIO()
