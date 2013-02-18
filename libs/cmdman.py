"""
$Id$
"""
from libs import exported
import shlex

class CmdMgr:
  def __init__(self):
    self.cmds = {}
    self.addCmd('help', 'Help', 'list', self.listCmds)
    self.addCmd('help', 'Help', 'default', self.listCmds)
    exported.registerevent('from_client_event', self.chkCmd, 1)

  def chkCmd(self, data):
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
        targs.insert(0, scmd)
        targs.insert(0, sname)
        if 'help' in targs:
          hindex = targs.index('help')
          try:
            del targs[targs.index(None)]
          except ValueError:
            pass
          try:
            del targs[targs.index('help')]            
          except ValueError:
            pass
          self.listCmds(targs)
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
              exported.sendtoclient("@R%s.%s@W is not a command" % (sname, scmd))
            else:
              retvalue = self.cmds[sname][stcmd]['func'](targs)
                
              if isinstance(retvalue, tuple):
                retval = retvalue[0]
                msg = retvalue[1]
              else:
                retval = retvalue
                msg = []
                
              if retval:
                if msg and isinstance(msg, list):
                  msg.insert(0, '')
                  msg.insert(1, '#bp.%s.%s' % (sname, stcmd))
                  msg.insert(2, '@G' + '-' * 60 + '@w')
                  msg.append('@G' + '-' * 60 + '@w')                  
                  msg.append('')
                  exported.sendtoclient('\n'.join(msg))
              else:
                self.listCmds([sname, scmd])              
          else:  
            exported.sendtoclient("@R%s.%s@W is not a command." % (sname, scmd))
        else:
          try:
            del targs[targs.index(None)]
          except ValueError:
            pass
          try:
            del targs[targs.index('help')]            
          except ValueError:
            pass
          self.listCmds(targs)
        return {'fromdata':''}
    else:
      return data
    
  def addCmd(self, sname, lname, cmd, tfunction, shelp="", lhelp=""):
    if not (sname in self.cmds):
      self.cmds[sname] = {}
    self.cmds[sname][cmd] = {'func':tfunction, 'lname':lname, 'lhelp':lhelp, 'shelp':shelp}
    
  def removeCmd(self, sname, cmd):
    if sname in self.cmds and cmd in self.cmds[sname]:
      del self.cmds[sname][cmd]
    
  def setDefault(self, sname, cmd):
    if sname in self.cmds and cmd in self.cmds[sname]:
      self.cmds[sname]['default'] = self.cmds[sname][cmd]
    
  def listCmds(self, args):
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
            thelp = self.cmds[sname][cmd]['func'].__doc__ % {'name':self.cmds[sname][cmd]['lname'], 'cmdname':cmd}
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
            
  def resetPluginCmds(self, sname):
    if sname in self.cmds:
      del self.cmds[sname]
      
  def load(self):
    exported.registerevent('from_client_event', self.chkCmd, 1)
    
    