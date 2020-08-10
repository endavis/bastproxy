"""
this module is for saving settings that should not appear in memory
the setting is saved to a file with read only permissions for the user
the proxy is running under

## Using
See the source for [net.net](/bastproxy/plugins/net/net.html)
for an example of using this plugin

'''python
    ssc = self.api('ssc.baseclass')()
    self.apikey = ssc('somepassword', self, desc='Password for something')
'''
"""
import os
import stat

import libs.argp as argp
from plugins._baseplugin import BasePlugin

NAME = 'Secret Setting Class'
SNAME = 'ssc'
PURPOSE = 'Class to save settings that should not stay in memory'
AUTHOR = 'Bast'
VERSION = 1

REQUIRED = True

class SSC(object):
  """
  a class to manage settings
  """
  def __init__(self, sshort_name, plugin, **kwargs):
    """
    initialize the class
    """
    self.sshort_name = sshort_name
    self.plugin = plugin
    self.short_name = plugin.short_name
    self.name = plugin.name
    self.api = plugin.api

    if 'default' in kwargs:
      self.default = kwargs['default']
    else:
      self.default = ''

    if 'desc' in kwargs:
      self.desc = kwargs['desc']
    else:
      self.desc = 'setting'

    self.api('api.add')(self.sshort_name, self.getss)

    parser = argp.ArgumentParser(add_help=False,
                                 description='set the %s' % self.desc)
    parser.add_argument('value',
                        help=self.desc,
                        default='',
                        nargs='?')
    self.api('commands.add')(self.sshort_name,
                             self.cmd_setssc,
                             showinhistory=False,
                             parser=parser)


  # read the secret from a file
  def getss(self):
    """
    read the secret from a file
    """
    first_line = ''
    filen = os.path.join(self.plugin.save_directory, self.sshort_name)
    try:
      with open(filen, 'r') as fileo:
        first_line = fileo.readline()

      return first_line.strip()
    except IOError:
      self.api('send.error')('Please set the %s with %s.%s.%s' % (self.desc,
                                                                  self.api('commands.prefix')(),
                                                                  self.short_name,
                                                                  self.sshort_name))

    return self.default

  def cmd_setssc(self, args):
    """
    set the secret
    """
    if args['value']:
      filen = os.path.join(self.plugin.save_directory, self.sshort_name)
      sscfile = open(filen, 'w')
      sscfile.write(args['value'])
      os.chmod(filen, stat.S_IRUSR | stat.S_IWUSR)
      return True, ['%s saved' % self.desc]

    return True, ['Please enter the %s' % self.desc]

class Plugin(BasePlugin):
  """
  a plugin to handle secret settings
  """
  def __init__(self, *args, **kwargs):
    BasePlugin.__init__(self, *args, **kwargs)

    self.reload_dependents_f = True

    self.api('api.add')('baseclass', self.api_baseclass)

  def initialize(self):
    """
    initialize the plugin
    """
    BasePlugin.initialize(self)

  # return the secret setting baseclass
  def api_baseclass(self):
    # pylint: disable=no-self-use
    """
    return the sql baseclass
    """
    return SSC
