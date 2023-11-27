# -*- coding: utf-8 -*-
# Project: bastproxy
# Filename: libs/api/_addapi.py
#
# File Description: hold the decorator to add items to the api
#
# By: Bast
"""
Use this decorator to add a function to the api

Example:
    @AddAPI('get.data.directory', description='get the data directory for this plugin')
    def _api_get_data_directory(self):
        \""" get the data directory for this plugin \"""
        return self.plugin_info.data_directory
"""
# Standard Library

# Third Party

# Project


class AddAPI:
    def __init__(self, api: str, description='', instance=False):
        """
        kwargs:
            event_name: the event to register to
            priority: the priority to register the function with (Default: 50)
        """
        self.api_name = api
        self.description = description
        self.instance = instance

    def __call__(self, func):
        func.api = {'name': self.api_name,
                    'description':self.description,
                    'instance':self.instance,
                    'addedin':{}}

        return func
