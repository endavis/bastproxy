"""
This module will do both debugging and logging
"""
from __future__ import print_function
import sys
import time
import os
import zipfile

import libs.argp as argp
from libs.persistentdict import PersistentDict
from plugins._baseplugin import BasePlugin

NAME = 'Logging'
SNAME = 'log'
PURPOSE = 'Handle logging to file and console, errors'
AUTHOR = 'Bast'
VERSION = 1
PRIORITY = 5

REQUIRED = True

class Plugin(BasePlugin):
  """
  a class to manage logging
  """
  def __init__(self, *args, **kwargs):
    """
    init the class
    """
    BasePlugin.__init__(self, *args, **kwargs)

    self.can_reload_f = False

    self.log_directory = os.path.join(self.api.BASEPATH, 'data', 'logs')

    try:
      os.makedirs(self.save_directory)
    except OSError:
      pass
    self.datatypes = {}
    self.datatypes_to_client = PersistentDict(
        os.path.join(self.save_directory, 'datatypes_to_client.txt'),
        'c')
    self.datatypes_to_console = PersistentDict(
        os.path.join(self.save_directory, 'datatypes_to_console.txt'),
        'c')
    self.datatypes_to_file = PersistentDict(
        os.path.join(self.save_directory, 'datatypes_to_file.txt'),
        'c')
    self.log_file_information = {}
    self.colors = {}

    self.template_for_log_file_name = '%a-%b-%d-%Y.log'
    #self.datatypes_to_file['default'] = {
                                #'log_directory':os.path.join(self.log_directory, 'default'),
                                #'file':'%a-%b-%d-%Y.log', 'timestamp':True
                                  #}

    self.colors['error'] = '@x136'

    # new api format
    self.api('api:add')('message', self.api_msg)
    self.api('api:add')('add:datatype', self.api_adddtype)
    self.api('api:add')('toggle:to:console', self.api_toggletoconsole)
    self.api('api:add')('toggle:to:file', self.api_toggletofile)
    self.api('api:add')('toggle:to:client', self.api_toggletoclient)
    self.api('api:add')('write:to:file', self.api_writefile)

    # add some default datatypes
    self.api('core.log:add:datatype')('default')
    self.api('core.log:add:datatype')('frommud')
    self.api('core.log:add:datatype')('startup')
    self.api('core.log:add:datatype')('shutdown')
    self.api('core.log:add:datatype')('error')

    # log some datatypes by default
    self.api('core.log:toggle:to:client')('error')
    self.api('core.log:toggle:to:console')('error')
    self.api('core.log:toggle:to:console')('default')
    self.api('core.log:toggle:to:console')('startup')
    self.api('core.log:toggle:to:console')('shutdown')

    self.dependencies = ['core.events']

  def api_writefile(self, dtype, data, stripcolor=False):
    """
    write directly to a file
    """
    if dtype not in self.datatypes_to_file:
      self.api('%s.file' % self.plugin_id)(dtype)

    if stripcolor and self.api('api:has')('core.colors:ansicode:strip'):
      data = self.api('core.colors:ansicode:strip')(data)

    tfile = os.path.join(self.log_directory, dtype,
                         time.strftime(self.datatypes_to_file[dtype]['file'],
                                       time.localtime()))
    if not os.path.exists(os.path.join(self.log_directory, dtype)):
      os.makedirs(os.path.join(self.log_directory, dtype, 'archive'))
    if (dtype not in self.log_file_information) or \
      (dtype in self.log_file_information and not self.log_file_information[dtype]):
      self.log_file_information[dtype] = {}
      self.log_file_information[dtype]['filename'] = tfile
      self.log_file_information[dtype]['fhandle'] = None
    elif tfile != self.log_file_information[dtype]['filename']:
      self.archivelog(dtype)
      self.log_file_information[dtype]['filename'] = tfile

    if not self.log_file_information[dtype]['fhandle']:
      self.log_file_information[dtype]['fhandle'] = \
                      open(self.log_file_information[dtype]['filename'], 'a')

    if self.datatypes_to_file[dtype]['timestamp']:
      tstring = '%s : ' % \
            (time.strftime(self.api.time_format, time.localtime()))
      data = tstring + data

    if self.api('api:has')('core.colors:ansicode:strip'):
      self.log_file_information[dtype]['fhandle'].write(
          self.api('core.colors:ansicode:strip')(data) + '\n')
    else:
      self.log_file_information[dtype]['fhandle'].write(data + '\n')
    self.log_file_information[dtype]['fhandle'].flush()
    return True

  # add a datatype to the log
  def api_adddtype(self, datatype):
    """  add a datatype
    @Ydatatype@w  = the datatype to add

    this function returns no values"""
    if datatype not in self.datatypes:
      self.datatypes[datatype] = True
      self.datatypes_to_client[datatype] = False
      self.datatypes_to_console[datatype] = False

  # process a message, use send:msg instead for the api
  def api_msg(self, msg, tags=None):
    """  send a message
    @Ymsg@w        = This message to send
    @Ydatatype@w   = the type to toggle

    this function returns no values"""
    senttoconsole = False
    senttoclient = False

    ttime = time.strftime(self.api.time_format, time.localtime())

    self.logtofile(msg, 'default')

    for dtag in tags:
      if dtag and dtag != 'None' \
            and dtag != 'default':

        tstring = '%s - %-15s : ' % (ttime, dtag)
        timestampmsg = tstring + msg

        self.logtofile(msg, dtag)

        if self.api('api:has')('core.colors:colorcode:to:ansicode') and \
            dtag in self.colors:
          timestampmsg = self.api('core.colors:colorcode:to:ansicode')(
              self.colors[dtag] + timestampmsg)

        if dtag in self.datatypes_to_client and self.datatypes_to_client[dtag] and not senttoclient:
          self.api('send:client')(timestampmsg)
          senttoclient = True

        if dtag in self.datatypes_to_console and self.datatypes_to_console[dtag] and not senttoconsole:
          print(timestampmsg, file=sys.stderr)
          senttoconsole = True

  # archive a log fle
  def archivelog(self, dtype):
    """
    archive the previous log
    """
    tfile = os.path.split(self.log_file_information[dtype]['filename'])[-1]
    self.log_file_information[dtype]['fhandle'].close()
    self.log_file_information[dtype]['fhandle'] = None

    backupfile = os.path.join(self.log_directory, dtype,
                              tfile)
    backupzipfile = os.path.join(self.log_directory, dtype, 'archive',
                                 tfile + '.zip')
    with zipfile.ZipFile(backupzipfile, 'w', zipfile.ZIP_DEFLATED,
                         allowZip64=True) as myzip:
      myzip.write(backupfile, arcname=self.log_file_information[dtype]['filename'])
    os.remove(backupfile)

  # log something to a file
  def logtofile(self, msg, dtype, stripcolor=True):
    """
    send a message to a log file
    """
    #print('logging', dtype)
    if dtype in self.datatypes_to_file and self.datatypes_to_file[dtype]['file']:
      return self.api('%s:write:to:file'% self.plugin_id)(dtype, msg, stripcolor)

    return False

  # toggle logging a datatype to the clients
  def api_toggletoclient(self, datatype, flag=True):
    """  toggle a data type to show to clients
    @Ydatatype@w  = the type to toggle, can be multiple (list)
    @Yflag@w      = True to send to clients, false otherwise (default: True)

    this function returns no values"""
    if datatype in self.datatypes_to_client and datatype != 'frommud':
      self.datatypes_to_client[datatype] = flag

    self.api('send:msg')('setting %s to log to client' % \
                      datatype)

    self.datatypes_to_client.sync()

  # toggle logging datatypes to the clients
  def cmd_client(self, args):
    """
    toggle datatypes shown to client
    """
    tmsg = []
    if args['datatype']:
      for i in args['datatype']:
        if i in self.datatypes_to_client and i != 'frommud':
          self.datatypes_to_client[i] = not self.datatypes_to_client[i]
          if self.datatypes_to_client[i]:
            tmsg.append('sending %s to client' % i)
          else:
            tmsg.append('no longer sending %s to client' % i)

        elif i != 'frommud':
          tmsg.append('Type %s does not exist' % i)
      self.datatypes_to_client.sync()
      return True, tmsg

    tmsg.append('Current types going to client')
    for i in self.datatypes_to_client:
      if self.datatypes_to_client[i]:
        tmsg.append(i)
    return True, tmsg

  # toggle logging a datatype to the console
  def api_toggletoconsole(self, datatype, flag=True):
    """  toggle a data type to show to console
    @Ydatatype@w  = the type to toggle
    @Yflag@w      = True to send to console, false otherwise (default: True)

    this function returns no values"""
    if datatype in self.datatypes_to_console and datatype != 'frommud':
      self.datatypes_to_console[datatype] = flag

    self.api('send:msg')('setting %s to log to console' % \
                      datatype, self.plugin_id)

    self.datatypes_to_console.sync()

  # toggle logging datatypes to the console
  def cmd_console(self, args):
    """
    log datatypes to the console
    """
    tmsg = []
    if args['datatype']:
      for i in args['datatype']:
        if i in self.datatypes_to_console and i != 'frommud':
          self.datatypes_to_console[i] = not self.datatypes_to_console[i]
          if self.datatypes_to_console[i]:
            tmsg.append('sending %s to console' % i)
          else:
            tmsg.append('no longer sending %s to console' % i)

        elif i != 'frommud':
          tmsg.append('Type %s does not exist' % i)
      self.datatypes_to_console.sync()
      return True, tmsg

    tmsg.append('Current types going to console')
    for i in self.datatypes_to_console:
      if self.datatypes_to_console[i]:
        tmsg.append(i)
    return True, tmsg

  # toggle logging a datatype to a file
  def api_toggletofile(self, datatype, timestamp=True):
    """  toggle a data type to show to file
    @Ydatatype@w  = the type to toggle
    @Yflag@w      = True to send to file, false otherwise (default: True)

    this function returns no values"""
    if datatype in self.datatypes_to_file:
      if self.log_file_information[datatype]['fhandle']:
        self.log_file_information[datatype]['fhandle'].close()
        self.log_file_information[datatype]['fhandle'] = None
      del self.datatypes_to_file[datatype]
    else:
      self.datatypes_to_file[datatype] = {'file':self.template_for_log_file_name,
                                          'timestamp':timestamp}
      self.api('send:msg')('setting %s to log to %s' % \
                      (datatype, self.datatypes_to_file[datatype]['file']),
                           self.plugin_id)
    self.datatypes_to_file.sync()

  # toggle a datatype to log to a file
  def cmd_file(self, args):
    """
    toggle a datatype to log to a file
    """
    tmsg = []
    timestamp = True
    if args['datatype'] != 'list':
      dtype = args['datatype']
      timestamp = args['notimestamp']

      if dtype in self.datatypes_to_file:
        if dtype in self.log_file_information:
          self.log_file_information[dtype]['fhandle'].close()
          self.log_file_information[dtype]['fhandle'] = None
        del self.datatypes_to_file[dtype]
        tmsg.append('removing %s from logging' % dtype)
      else:
        self.datatypes_to_file[dtype] = {'file':self.template_for_log_file_name,
                                         'log_directory':os.path.join(self.log_directory, dtype),
                                         'timestamp':timestamp}
        tmsg.append('setting %s to log to %s' % \
                        (dtype, self.datatypes_to_file[dtype]['file']))
        self.datatypes_to_file.sync()
      return True, tmsg
    else:
      tmsg.append('Current types going to file')
      for i in self.datatypes_to_file:
        if self.datatypes_to_file[i]:
          tmsg.append('%s - %s - %s' % \
             (i, self.datatypes_to_file[i]['file'], self.datatypes_to_file[i]['timestamp']))
      return True, tmsg

  # archive a datatype
  def cmd_archive(self, args):
    """
    archive a datatype
    """
    tmsg = []
    if args:
      for i in args:
        if i in self.datatypes:
          self.archivelog(i)
        else:
          tmsg.append('%s does not exist' % i)
      return True, tmsg

    tmsg = ['Please specifiy a datatype to archive']
    return False, tmsg

  # show all types
  def cmd_types(self, args):
    """
    list data types
    """
    tmsg = []
    tmsg.append('Data Types')
    tmsg.append('-' *  30)
    match = args['match']
    tkeys = self.datatypes.keys()
    tkeys.sort()
    for i in tkeys:
      if not match or match in i:
        tmsg.append(i)
    return True, tmsg

  def logmud(self, args):
    """
    log all data from the mud
    """
    if 'frommud' in self.datatypes_to_file and self.datatypes_to_file['frommud']['file']:
      if args['eventname'] == 'from_mud_event':
        data = args['noansi']
      elif args['eventname'] == 'to_mud_event':
        data = 'tomud: ' + args['data'].strip()
      self.logtofile(data, 'frommud', stripcolor=False)
    return args

  def initialize(self):
    """
    initialize external stuff
    """
    BasePlugin.initialize(self)

    #print('log api before adding', self.api.api)

    #print('log api after adding', self.api.api)
    self.api('core.events:register:to:event')('from_mud_event', self.logmud)
    self.api('core.events:register:to:event')('to_mud_event', self.logmud)
    self.api('core.events:register:to:event')('{0.plugin_id}_savestate'.format(self), self._savestate)

    parser = argp.ArgumentParser(add_help=False,
                                 description="""toggle datatypes to clients

      if no arguments, data types that are currenty sent to clients will be listed""")
    parser.add_argument('datatype',
                        help='a list of datatypes to toggle',
                        default=[],
                        nargs='*')
    self.api('core.commands:command:add')('client',
                                          self.cmd_client,
                                          lname='Logger',
                                          parser=parser)

    parser = argp.ArgumentParser(add_help=False,
                                 description="""toggle datatype to log to a file

      the file will be located in the data/logs/<dtype> directory

      the filename for the log will be <date>.log
          Example: Tue-Feb-26-2013.log

      if no arguments, types that are sent to file will be listed""")
    parser.add_argument('datatype',
                        help='the datatype to toggle',
                        default='list',
                        nargs='?')
    parser.add_argument("-n",
                        "--notimestamp",
                        help="do not log to file with a timestamp",
                        action="store_false")
    self.api('core.commands:command:add')('file',
                                          self.cmd_file,
                                          lname='Logger',
                                          parser=parser)

    parser = argp.ArgumentParser(add_help=False,
                                 description="""toggle datatypes to the console

      if no arguments, data types that are currenty sent to the console will be listed""")
    parser.add_argument('datatype',
                        help='a list of datatypes to toggle',
                        default=[],
                        nargs='*')
    self.api('core.commands:command:add')('console',
                                          self.cmd_console,
                                          lname='Logger',
                                          parser=parser)

    parser = argp.ArgumentParser(add_help=False,
                                 description="list all datatypes")
    parser.add_argument('match',
                        help='only list datatypes that have this argument in their name',
                        default='',
                        nargs='?')
    self.api('core.commands:command:add')('types',
                                          self.cmd_types,
                                          lname='Logger',
                                          parser=parser)

    #print('log loaded')

  def _savestate(self, _=None):
    """
    save items not covered by baseplugin class
    """
    self.datatypes_to_client.sync()
    self.datatypes_to_file.sync()
    self.datatypes_to_console.sync()
