# Project: bastproxy
# Filename: plugins/client/mapper/plugin/__init__.py
#
# File Description: a plugin that stores the map, finds paths and walks them
#
# By: Bast

__all__ = ["Plugin"]

from ._mapper import MapperPlugin as Plugin
