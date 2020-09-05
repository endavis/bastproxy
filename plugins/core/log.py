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

    #print('log api.api', self.api.api)
    #print('log basepath', self.api.BASEPATH)
    self.save_directory = os.path.join(self.api.BASEPATH, 'data',
                                       'plugins', self.short_name)
    self.logdir = os.path.join(self.api.BASEPATH, 'data', 'logs')
    #print('logdir', self.logdir)
    try:
      os.makedirs(self.save_directory)
    except OSError:
      pass
    self.dtypes = {}
    self.sendtoclient = PersistentDict(
        os.path.join(self.save_directory, 'sendtoclient.txt'),
        'c')
    self.sendtoconsole = PersistentDict(
        os.path.join(self.save_directory, 'sendtoconsole.txt'),
        'c')
    self.sendtofile = PersistentDict(
        os.path.join(self.save_directory, 'sendtofile.txt'),
        'c')
    self.currentlogs = {}
    self.colors = {}

    self.filenametemplate = '%a-%b-%d-%Y.log'
    #self.sendtofile['default'] = {
                                #'logdir':os.path.join(self.logdir, 'default'),
                                #'file':'%a-%b-%d-%Y.log', 'timestamp':True
                                  #}

    self.colors['error'] = '@x136'

    self.api('api.add')('msg', self.api_msg)
    self.api('api.add')('adddtype', self.api_adddtype)
    self.api('api.add')('console', self.api_toggletoconsole)
    self.api('api.add')('file', self.api_toggletofile)
    self.api('api.add')('client', self.api_toggletoclient)
    self.api('api.add')('writefile', self.api_writefile)

    # add some default datatypes
    self.api('log.adddtype')('default')
    self.api('log.adddtype')('frommud')
    self.api('log.adddtype')('startup')
    self.api('log.adddtype')('shutdown')
    self.api('log.adddtype')('error')

    # log some datatypes by default
    self.api('log.client')('error')
    self.api('log.console')('error')
    self.api('log.console')('default')
    self.api('log.console')('startup')
    self.api('log.console')('shutdown')

    self.dependencies = ['core.events']

  def api_writefile(self, dtype, data, stripcolor=False):
    """
    write directly to a file
    """
    if dtype not in self.sendtofile:
      self.api('%s.file' % self.short_name)(dtype)

    if stripcolor and self.api('api.has')('colors.stripansi'):
      data = self.api('colors.stripansi')(data)

    tfile = os.path.join(self.logdir, dtype,
                         time.strftime(self.sendtofile[dtype]['file'],
                                       time.localtime()))
    if not os.path.exists(os.path.join(self.logdir, dtype)):
      os.makedirs(os.path.join(self.logdir, dtype, 'archive'))
    if (dtype not in self.currentlogs) or \
      (dtype in self.currentlogs and not self.currentlogs[dtype]):
      self.currentlogs[dtype] = {}
      self.currentlogs[dtype]['filename'] = tfile
      self.currentlogs[dtype]['fhandle'] = None
    elif tfile != self.currentlogs[dtype]['filename']:
      self.archivelog(dtype)
      self.currentlogs[dtype]['filename'] = tfile

    if not self.currentlogs[dtype]['fhandle']:
      self.currentlogs[dtype]['fhandle'] = \
                      open(self.currentlogs[dtype]['filename'], 'a')

    if self.sendtofile[dtype]['timestamp']:
      tstring = '%s : ' % \
            (time.strftime(self.api.time_format, time.localtime()))
      data = tstring + data

    if self.api('api.has')('colors.stripansi'):
      self.currentlogs[dtype]['fhandle'].write(
          self.api('colors.stripansi')(data) + '\n')
    else:
      self.currentlogs[dtype]['fhandle'].write(data + '\n')
    self.currentlogs[dtype]['fhandle'].flush()
    return True

  # add a datatype to the log
  def api_adddtype(self, datatype):
    """  add a datatype
    @Ydatatype@w  = the datatype to add

    this function returns no values"""
    if datatype not in self.dtypes:
      self.dtypes[datatype] = True
      self.sendtoclient[datatype] = False
      self.sendtoconsole[datatype] = False

  # process a message, use send.msg instead for the api
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

        if self.api('api.has')('colors.convertcolors') and \
            dtag in self.colors:
          timestampmsg = self.api('colors.convertcolors')(
              self.colors[dtag] + timestampmsg)

        if dtag in self.sendtoclient and self.sendtoclient[dtag] and not senttoclient:
          self.api('send.client')(timestampmsg)
          senttoclient = True

        if dtag in self.sendtoconsole and self.sendtoconsole[dtag] and not senttoconsole:
          print(timestampmsg, file=sys.stderr)
          senttoconsole = True

  # archive a log fle
  def archivelog(self, dtype):
    """
    archive the previous log
    """
    tfile = os.path.split(self.currentlogs[dtype]['filename'])[-1]
    self.currentlogs[dtype]['fhandle'].close()
    self.currentlogs[dtype]['fhandle'] = None

    backupfile = os.path.join(self.logdir, dtype,
                              tfile)
    backupzipfile = os.path.join(self.logdir, dtype, 'archive',
                                 tfile + '.zip')
    with zipfile.ZipFile(backupzipfile, 'w', zipfile.ZIP_DEFLATED,
                         allowZip64=True) as myzip:
      myzip.write(backupfile, arcname=self.currentlogs[dtype]['filename'])
    os.remove(backupfile)

  # log something to a file
  def logtofile(self, msg, dtype, stripcolor=True):
    """
    send a message to a log file
    """
    #print('logging', dtype)
    if dtype in self.sendtofile and self.sendtofile[dtype]['file']:
      return self.api('%s.writefile'% self.short_name)(dtype, msg, stripcolor)

    return False

  # toggle logging a datatype to the clients
  def api_toggletoclient(self, datatype, flag=True):
    """  toggle a data type to show to clients
    @Ydatatype@w  = the type to toggle, can be multiple (list)
    @Yflag@w      = True to send to clients, false otherwise (default: True)

    this function returns no values"""
    if datatype in self.sendtoclient and datatype != 'frommud':
      self.sendtoclient[datatype] = flag

    self.api('send.msg')('setting %s to log to client' % \
                      datatype)

    self.sendtoclient.sync()

  # toggle logging datatypes to the clients
  def cmd_client(self, args):
    """
    toggle datatypes shown to client
    """
    tmsg = []
    if args['datatype']:
      for i in args['datatype']:
        if i in self.sendtoclient and i != 'frommud':
          self.sendtoclient[i] = not self.sendtoclient[i]
          if self.sendtoclient[i]:
            tmsg.append('sending %s to client' % i)
          else:
            tmsg.append('no longer sending %s to client' % i)

        elif i != 'frommud':
          tmsg.append('Type %s does not exist' % i)
      self.sendtoclient.sync()
      return True, tmsg

    tmsg.append('Current types going to client')
    for i in self.sendtoclient:
      if self.sendtoclient[i]:
        tmsg.append(i)
    return True, tmsg

  # toggle logging a datatype to the console
  def api_toggletoconsole(self, datatype, flag=True):
    """  toggle a data type to show to console
    @Ydatatype@w  = the type to toggle
    @Yflag@w      = True to send to console, false otherwise (default: True)

    this function returns no values"""
    if datatype in self.sendtoconsole and datatype != 'frommud':
      self.sendtoconsole[datatype] = flag

    self.api('send.msg')('setting %s to log to console' % \
                      datatype, self.short_name)

    self.sendtoconsole.sync()

  # toggle logging datatypes to the console
  def cmd_console(self, args):
    """
    log datatypes to the console
    """
    tmsg = []
    if args['datatype']:
      for i in args['datatype']:
        if i in self.sendtoconsole and i != 'frommud':
          self.sendtoconsole[i] = not self.sendtoconsole[i]
          if self.sendtoconsole[i]:
            tmsg.append('sending %s to console' % i)
          else:
            tmsg.append('no longer sending %s to console' % i)

        elif i != 'frommud':
          tmsg.append('Type %s does not exist' % i)
      self.sendtoconsole.sync()
      return True, tmsg

    tmsg.append('Current types going to console')
    for i in self.sendtoconsole:
      if self.sendtoconsole[i]:
        tmsg.append(i)
    return True, tmsg

  # toggle logging a datatype to a file
  def api_toggletofile(self, datatype, timestamp=True):
    """  toggle a data type to show to file
    @Ydatatype@w  = the type to toggle
    @Yflag@w      = True to send to file, false otherwise (default: True)

    this function returns no values"""
    if datatype in self.sendtofile:
      if self.currentlogs[datatype]['fhandle']:
        self.currentlogs[datatype]['fhandle'].close()
        self.currentlogs[datatype]['fhandle'] = None
      del self.sendtofile[datatype]
    else:
      self.sendtofile[datatype] = {'file':self.filenametemplate,
                                   'timestamp':timestamp}
      self.api('send.msg')('setting %s to log to %s' % \
                      (datatype, self.sendtofile[datatype]['file']),
                           self.short_name)
    self.sendtofile.sync()

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

      if dtype in self.sendtofile:
        if dtype in self.currentlogs:
          self.currentlogs[dtype]['fhandle'].close()
          self.currentlogs[dtype]['fhandle'] = None
        del self.sendtofile[dtype]
        tmsg.append('removing %s from logging' % dtype)
      else:
        self.sendtofile[dtype] = {'file':self.filenametemplate,
                                  'logdir':os.path.join(self.logdir, dtype),
                                  'timestamp':timestamp}
        tmsg.append('setting %s to log to %s' % \
                        (dtype, self.sendtofile[dtype]['file']))
        self.sendtofile.sync()
      return True, tmsg
    else:
      tmsg.append('Current types going to file')
      for i in self.sendtofile:
        if self.sendtofile[i]:
          tmsg.append('%s - %s - %s' % \
             (i, self.sendtofile[i]['file'], self.sendtofile[i]['timestamp']))
      return True, tmsg

  # archive a datatype
  def cmd_archive(self, args):
    """
    archive a datatype
    """
    tmsg = []
    if args:
      for i in args:
        if i in self.dtypes:
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
    tkeys = self.dtypes.keys()
    tkeys.sort()
    for i in tkeys:
      if not match or match in i:
        tmsg.append(i)
    return True, tmsg

  def logmud(self, args):
    """
    log all data from the mud
    """
    if 'frommud' in self.sendtofile and self.sendtofile['frommud']['file']:
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
    self.api('events.register')('from_mud_event', self.logmud)
    self.api('events.register')('to_mud_event', self.logmud)
    self.api('events.register')('plugin_%s_savestate' % self.short_name, self._savestate)

    parser = argp.ArgumentParser(add_help=False,
                                 description="""toggle datatypes to clients

      if no arguments, data types that are currenty sent to clients will be listed""")
    parser.add_argument('datatype',
                        help='a list of datatypes to toggle',
                        default=[],
                        nargs='*')
    self.api('commands.add')('client',
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
    self.api('commands.add')('file',
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
    self.api('commands.add')('console',
                             self.cmd_console,
                             lname='Logger',
                             parser=parser)

    parser = argp.ArgumentParser(add_help=False,
                                 description="list all datatypes")
    parser.add_argument('match',
                        help='only list datatypes that have this argument in their name',
                        default='',
                        nargs='?')
    self.api('commands.add')('types',
                             self.cmd_types,
                             lname='Logger',
                             parser=parser)

    #print('log loaded')

  def _savestate(self, _=None):
    """
    save items not covered by baseplugin class
    """
    self.sendtoclient.sync()
    self.sendtofile.sync()
    self.sendtoconsole.sync()
