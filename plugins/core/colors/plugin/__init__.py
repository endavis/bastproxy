# -*- coding: utf-8 -*-
# Project: bastproxy
# Filename: plugins/core/colors/_init_.py
#
# File Description: a plugin to handle ansi and xterm colors
#
# By: Bast
"""
This plugin handles colors

## Color Codes
### Ansi

|| color   ||   regular   ||     bold     ||
|| Red     ||   @r@@r@w   ||     @R@@R@w  ||
|| Green   ||   @g@@g@w   ||     @g@@G@w  ||
|| Yellow  ||   @y@@y@w   ||     @Y@@Y@w  ||
|| Blue    ||   @b@@b@w   ||     @B@@B@w  ||
|| Magenta ||   @m@@m@w   ||     @M@@M@w  ||
|| Cyan    ||   @c@@c@w   ||     @C@@C@w  ||
|| White   ||   @w@@w@w   ||     @W@@W@w  ||

### xterm 256

* @x154@@x154 - make text color xterm 154@w
* @z154@@z154@w - make background color xterm 154@w

"""
# these 4 are required
PLUGIN_NAME = 'Ansi/Xterm Colors'
PLUGIN_PURPOSE = 'Ansi/Xterm color functions'
PLUGIN_AUTHOR = 'Bast'
PLUGIN_VERSION = 1
PLUGIN_REQUIRED = True

__all__ = ['Plugin']

from ._colors import ColorsPlugin as Plugin
