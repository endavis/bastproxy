# Project: bastproxy
# Filename: plugins/core/ssc/_init_.py
#
# File Description: a plugin to save settings that should not stay in memory
#
# By: Bast
"""this plugin is for saving settings that should not appear in memory
the setting is saved to a file with read only permissions for the user
the proxy is running under.

## Using
See the source for [net.proxy](/bastproxy/plugins/net/proxy.html)
for an example of using this plugin

'''python
    ssc = self.plugin.api('plugins.core.ssc:baseclass.get')()
    self.plugin.apikey = ssc('somepassword', self, desc='Password for something')
'''
"""

# these 4 are required
PLUGIN_NAME = "Secret Setting Class"
PLUGIN_PURPOSE = "Class to save settings that should not stay in memory"
PLUGIN_AUTHOR = "Bast"
PLUGIN_VERSION = 1

PLUGIN_REQUIRED = True
