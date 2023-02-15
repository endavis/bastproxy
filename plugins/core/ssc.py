# -*- coding: utf-8 -*-
# Project: bastproxy
# Filename: plugins/core/ssc.py
#
# File Description: a plugin to save settings that should not stay in memory
#
# By: Bast
"""
this plugin is for saving settings that should not appear in memory
the setting is saved to a file with read only permissions for the user
the proxy is running under

## Using
See the source for [net.proxy](/bastproxy/plugins/net/proxy.html)
for an example of using this plugin

'''python
    ssc = self.plugin.api('plugins.core.ssc:baseclass:get')()
    self.plugin.apikey = ssc('somepassword', self, desc='Password for something')
'''
"""
# Standard Library
import os
import stat

# 3rd Party

# Project
import libs.argp as argp
from libs.records import LogRecord
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
    def __init__(self, name, plugin, **kwargs):
        """
        initialize the class
        """
        self.name = name
        self.plugin = plugin

        if 'default' in kwargs:
            self.default = kwargs['default']
        else:
            self.default = ''

        if 'desc' in kwargs:
            self.desc = kwargs['desc']
        else:
            self.desc = 'setting'

        self.plugin.api('libs.api:add')(f"ssc:{self.name}", self.getss)

        parser = argp.ArgumentParser(add_help=False,
                                     description=f"set the {self.desc}")
        parser.add_argument('value',
                            help=self.desc,
                            default='',
                            nargs='?')
        self.plugin.api('plugins.core.commands:command:add')(self.name,
                                                     self.cmd_setssc,
                                                     showinhistory=False,
                                                     parser=parser)


    # read the secret from a file
    def getss(self, quiet=False):
        """
        read the secret from a file
        """
        first_line = ''
        file_name = os.path.join(self.plugin.save_directory, self.name)
        try:
            with open(file_name, 'r') as fileo:
                first_line = fileo.readline()

            return first_line.strip()
        except IOError:
            if not quiet:
                LogRecord(f"getss - Please set the {self.desc} with {self.plugin.api('plugins.core.commands:get:command:prefix')()}.{self.plugin.plugin_id}.{self.name}",
                          level='error', sources=[self.plugin.plugin_id]).send()

        return self.default

    def cmd_setssc(self, args):
        """
        set the secret
        """
        if args['value']:
            file_name = os.path.join(self.plugin.save_directory, self.name)
            data_file = open(file_name, 'w')
            data_file.write(args['value'])
            os.chmod(file_name, stat.S_IRUSR | stat.S_IWUSR)
            return True, [f"{self.desc} saved"]

        return True, [f"Please enter the {self.desc}"]

class Plugin(BasePlugin):
    """
    a plugin to handle secret settings
    """
    def __init__(self, *args, **kwargs):
        BasePlugin.__init__(self, *args, **kwargs)

        self.reload_dependents_f = True

        self.api('libs.api:add')('baseclass:get', self.api_baseclass)

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
