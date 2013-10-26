"""
$Id$

This module handles commands and parsing input

#TODO: use decorators to handle the adding of commands?
"""
from libs.api import API
import shlex

class CmdMgr(object):
  """
  a class to manage internal commands
  """
  def __init__(self):
    """
    init the class
    """
    self.sname = 'commands'
    self.name = 'Commands'
    self.cmds = {}
    self.api = API()
    self.nomultiplecmds = {}
    self.regexlookup = {}
    self.lastcmd = ''

    self.api.add(self.sname, 'add', self.addcmd)
    self.api.add(self.sname, 'remove', self.removecmd)
    self.api.add(self.sname, 'default', self.setdefault)
    self.api.add(self.sname, 'removeplugin', self.removeplugin)

    self.addcmd('list', {'func':self.listcmds, 'shelp':'list commands'})
    self.addcmd('default', {'func':self.listcmds, 'shelp':'list commands'})

  def formatretmsg(self, msg, sname, stcmd):
    """
    format a return message
    """
    msg.insert(0, '')
    msg.insert(1, '#bp.%s.%s' % (sname, stcmd))
    msg.insert(2, '@G' + '-' * 60 + '@w')
    msg.append('@G' + '-' * 60 + '@w')
    msg.append('')
    return msg

  def runcmd(self, tfunction, targs, sname, stcmd, scmd):
    """
    run a command
    """
    retvalue = tfunction(targs)

    if isinstance(retvalue, tuple):
      retval = retvalue[0]
      msg = retvalue[1]
    else:
      retval = retvalue
      msg = []

    if retval:
      if msg and isinstance(msg, list):
        self.api.get('output.client')('\n'.join(self.formatretmsg(msg, sname, stcmd)))
        return True
    else:
      _, msg = self.listcmds([sname, scmd])
      self.api.get('output.client')('\n'.join(self.formatretmsg(
                                                  msg, 'plugins', 'help')))
    return retval

  def chkcmd(self, data):
    """
    check a line from a client for a command
    """
    tdat = data['fromdata']
    if tdat[0:3] == '#bp':
      cmd = tdat.split(" ")[0]
      args = tdat.replace(cmd, "").strip()
      targs = []
      targs = shlex.split(args)
      tst = cmd.split('.')
      try:
        sname = tst[1].strip()
      except IndexError:
        sname = None
      try:
        scmd = tst[2].strip()
      except IndexError:
        scmd = None
      if scmd:
        targs.insert(0, scmd)
      elif len(targs) > 0:
        scmd = targs[0]
      targs.insert(0, sname)
      if 'help' in targs:
        try:
          del targs[targs.index(None)]
        except ValueError:
          pass
        try:
          del targs[targs.index('help')]
        except ValueError:
          pass
        _, msg = self.listcmds(targs)
        self.api.get('output.client')('\n'.join(self.formatretmsg(
                                              msg, 'plugins', 'help')))
      elif sname and scmd:
        if sname in self.cmds:
          stcmd = None
          if scmd in self.cmds[sname]:
            stcmd = scmd
          elif not scmd and 'default' in self.cmds[sname]:
            stcmd = 'default'
          try:
            del targs[targs.index(scmd)]
          except ValueError:
            pass
          try:
            del targs[targs.index(sname)]
          except ValueError:
            pass
          if not stcmd:
            self.api.get('output.client')("@R%s.%s@W is not a command" % \
                                                        (sname, scmd))
          else:
            self.runcmd(self.cmds[sname][stcmd]['func'], targs,
                                                  sname, stcmd, scmd)
        else:
          self.api.get('output.client')("@R%s.%s@W is not a command." % \
                                                  (sname, scmd))
      else:
        try:
          del targs[targs.index(None)]
        except ValueError:
          pass
        try:
          del targs[targs.index('help')]
        except ValueError:
          pass
        _, msg = self.listcmds(targs)
        self.api.get('output.client')('\n'.join(self.formatretmsg(
                                                msg, 'plugins', 'help')))

      return {'fromdata':''}
    else:
      if tdat.strip() == self.lastcmd:
        if tdat in self.nomultiplecmds:
          data['fromdata'] = ''
      self.lastcmd = tdat.strip()

      return data

  # add a command
  def addcmd(self, cmdname, args):
    """  add a command
    @Ycmdname@w  = the base that the api should be under
    The @Yargs@w should contain
      @Yfunc@w   = the function that should be run when this command is executed
      @Yshelp@w  = the short help, a brief description of what the command does
      @Ylhelp@w  = a longer description of what the command does

      The command will be added as sname.cmdname

      sname is gotten from the class the function belongs to"""

    #lname, cmd, tfunction, shelp="", lhelp=""
    #{'func':tfunction, 'lname':lname, 'lhelp':lhelp, 'shelp':shelp}
    lname = None
    if not ('func' in args):
      self.api.get('output.msg')('cmd %s.%s has no function, not adding' % \
                                                (sname, cmdname), self.sname)
      return
    try:
      sname = args['func'].im_self.sname
    except AttributeError:
      self.api.get('output.msg')('Function is not part of a class: %s' % cmdname)
      return
    try:
      lname = args['func'].im_self.name
      args['lname'] = lname
    except AttributeError:
      pass

    if not ('lname' in args):
      self.api.get('output.msg')('cmd %s.%s has no long name, not adding' % \
                                                (sname, cmdname), self.sname)
      return
    if not (sname in self.cmds):
      self.cmds[sname] = {}
    self.cmds[sname][cmdname] = args

  # remove a command
  def removecmd(self, sname, cmdname):
    """  remove a command
    @Ysname@w    = the top level of the command
    @Ycmdname@w  = the name of the command"""
    if sname in self.cmds and cmdname in self.cmds[sname]:
      del self.cmds[sname][cmdname]
    else:
      self.api.get('output.msg')('removecmd: cmd %s.%s does not exist' % \
                                                (sname, cmdname), self.sname)

  # set the default command for a plugin
  def setdefault(self, sname, cmd):
    """  set the default command for a plugin
    @Ysname@w    = the plugin of the command
    @Ycmdname@w  = the name of the command"""
    if sname in self.cmds and cmd in self.cmds[sname]:
      self.cmds[sname]['default'] = self.cmds[sname][cmd]

  # remove all commands for a plugin
  def removeplugin(self, sname):
    """  remove all commands for a plugin
    @Ysname@w    = the plugin to remove commands for"""
    if sname in self.cmds:
      del self.cmds[sname]
    else:
      self.api.get('output.msg')('removeplugin: cmd %s does not exist' % sname, self.sname)

  def listcmds(self, args):
    """
    list commands
    """
    tmsg = []
    if len(args) > 0 and args[0]:
      sname = args[0]
      try:
        cmd = args[1]
      except IndexError:
        cmd = None
      if sname in self.cmds:
        if cmd and cmd in self.cmds[sname]:
          thelp = 'No help for this command'
          if self.cmds[sname][cmd]['func'].__doc__:
            thelp = self.cmds[sname][cmd]['func'].__doc__ % \
                      {'name':self.cmds[sname][cmd]['lname'], 'cmdname':cmd}
          elif self.cmds[sname][cmd]['shelp']:
            thelp = self.cmds[sname][cmd]['shelp']
          tmsg.append(thelp)
        else:
          tmsg.append('Commands in category: %s' % sname)
          for i in self.cmds[sname]:
            if i != 'default':
              tmsg.append('  %-10s : %s' % (i, self.cmds[sname][i]['shelp']))
      else:
        tmsg.append('There is no category named %s' % sname)
    else:
      tmsg.append('Command Categories:')
      for i in self.cmds:
        tmsg.append('  %s' % i)
    return True, tmsg

  def load(self):
    """
    load external stuff
    """
    self.api.get('managers.add')(self.sname, self)
    self.api.get('logger.adddtype')(self.sname)
    self.api.get('logger.console')(self.sname)
    self.api.get('events.register')('from_client_event', self.chkcmd, prio=1)
    self.api.get('events.eraise')('plugin_cmdman_loaded', {})

