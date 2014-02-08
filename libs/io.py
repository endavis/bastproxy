"""
$Id$

handle output functions
"""
import time
import sys
import traceback
import re
from libs.api import API
from libs import color

api = API()

errors = []

# send a message
def api_msg(tmsg, primary='default', secondary='None'):
  """  send a message through the log plugin
    @Ymsg@w        = This message to send
    @Yprimary@w    = the primary datatype of the message (default: 'default')
    @Ysecondary@w  = the secondary datatype of the message
                        (default: 'None')

  this function returns no values"""
  try:
    api.get('log.msg')({'msg':tmsg}, {'primary':primary, 'secondary':secondary})
  except (AttributeError, RuntimeError): #%s - %-10s :
    print '%s - %-10s : %s' % (time.strftime(api.timestring,
                                          time.localtime()), primary, tmsg)

# write and format a traceback
def api_traceback(message=""):
  """  handle a traceback
    @Ymessage@w  = the message to put into the traceback

  this function returns no values"""
  exc = "".join(traceback.format_exception(sys.exc_info()[0],
                    sys.exc_info()[1], sys.exc_info()[2]))

  if message:
    message = message + "\n" + exc
  else:
    message = exc

  api.get('output.error')(message)

# write and format an error
def api_error(text):
  """  handle an error
    @Ytext@w  = The error to handle

  this function returns no values"""
  text = str(text)
  test = []
  for i in text.split('\n'):
    test.append(color.convertcolors('@x136%s@w' % i))
  tmsg = '\n'.join(test)
  errors.append({'timestamp':time.strftime(api.timestring,
                                          time.localtime()),
                 'msg':tmsg})
  try:
    api.get('log.msg')({'msg':tmsg, 'primary':'error'})
  except (AttributeError, TypeError):
    print '%s - No Log Plugin - %s : %s' % (time.strftime(api.timestring,
                                          time.localtime()), 'error', tmsg)

# send text to the clients
def api_client(text, raw=False, preamble=True):
  """  handle a traceback
    @Ytext@w      = The text to send to the clients
    @Yraw@w       = if True, don't convert colors
    @Ypreamble@w  = if True, send the preamble

  this function returns no values"""
  if isinstance(text, basestring):
    text = text.split('\n')

  if not raw:
    test = []
    for i in text:
      if preamble:
        i = '@C#BP@w: ' + i
      test.append(color.convertcolors(i))
    text = test

  try:
    api.get('events.eraise')('to_client_event', {'original':'\n'.join(text),
                                    'raw':raw, 'dtype':'fromproxy'})
  except (NameError, TypeError, AttributeError):
    api.get('output.msg')("couldn't send msg to client: %s" % '\n'.join(text), primary='error')

# execute a command throgh the interpreter
def api_execute(command):
  """  execute a command through the interpreter
  It will first check to see if it is an internal command, and then
  send to the mud if not.
    @Ycommand@w      = the command to send through the interpreter

  this function returns no values"""
  data = None
  api.get('output.msg')('got command %s from client' % repr(command), primary='inputparse')

  if command == '\r\n':
    api.get('output.msg')('sending %s to the mud' % repr(command), primary='inputparse')
    api.get('events.eraise')('to_mud_event', {'data':command, 'dtype':'fromclient'})
    return

  command = command.strip()
  #if '\r\n' in command:
    #api.get('output.msg')('(has rn) got command %s from client' % repr(command), primary='inputparse')
  #else:
    #api.get('output.msg')('got command %s from client' % repr(command), primary='inputparse')

  commands = command.split('\r\n')

  for tcommand in commands:
    newdata = api.get('events.eraise')('from_client_event', {'fromdata':tcommand})

    if 'fromdata' in newdata:
      tcommand = newdata['fromdata']
      tcommand = tcommand.strip()

    if tcommand:
      datalist = re.split(api.splitre, tcommand)
      if len(datalist) > 1:
        api.get('output.msg')('broke %s into %s' % (tcommand, datalist), primary='inputparse')
        for cmd in datalist:
          api_execute(cmd)
      else:
        tcommand = tcommand.replace('||', '|')
        if tcommand[-1] != '\n':
          tcommand = tcommand + '\n'
        api.get('output.msg')('sending %s to the mud' % tcommand.strip(), primary='inputparse')
        api.get('events.eraise')('to_mud_event', {'data':tcommand, 'dtype':'fromclient'})

# send data directly to the mud
def api_tomud(data):
  """ send data directly to the mud

  This does not go through the interpreter
    @Ydata@w     = the data to send

  this function returns no values
  """
  api.get('events.eraise')('to_mud_event', {'data':data, 'dtype':'fromclient'})


api.add('output', 'msg', api_msg)
api.add('output', 'error', api_error)
api.add('output', 'traceback', api_traceback)
api.add('output', 'client', api_client)
api.add('output', 'tomud', api_tomud)
api.add('input', 'execute', api_execute)
