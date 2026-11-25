# Project: bastproxy
# Filename: plugins/core/web/__init__.py
#
# File Description: a plugin that serves web pages for plugins
#
# By: Bast
"""This plugin runs a small GET-only web server that plugins publish pages through.

APIs:
  ``web.page.add(owner, title, lines)`` stores one page and returns its token link.

See `docs/web-server.md` for the settings, the security model and the setups, and
`docs/claude/web_system.md` for the plugin developer view.
"""

# these 4 are required
PLUGIN_NAME = "Web Server"
PLUGIN_PURPOSE = "serve web pages that plugins publish"
PLUGIN_AUTHOR = "Bast"
PLUGIN_VERSION = 1

PLUGIN_REQUIRED = True
