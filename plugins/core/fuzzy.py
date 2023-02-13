# -*- coding: utf-8 -*-
# Project: bastproxy
# Filename: plugins/core/fuzzy.py
#
# File Description: a plugin to do fuzzy matching with strings
#
# By: Bast
"""
This plugin holds an api to do fuzzy matching
"""
# Standard Library
import sys

# 3rd Party
try:
    from fuzzywuzzy import process
except ImportError:
    print('Please install required libraries. fuzzywuzzy is missing.')
    print('From the root of the project: pip(3) install -r requirements.txt')
    sys.exit(1)

# Project
from plugins._baseplugin import BasePlugin
from libs.record import LogRecord

NAME = 'Fuzzy Match'
SNAME = 'fuzzy'
PURPOSE = 'do fuzzy matching'
AUTHOR = 'Bast'
VERSION = 1
REQUIRED = True

def sort_fuzzy_result(result):
    """
    sort a result from extract
    """
    newdict = {}
    for i in result:
        if not i[1] in newdict:
            newdict[i[1]] = []
        newdict[i[1]].append(i[0])
    return newdict

class Plugin(BasePlugin):
    """
    a plugin to test command parsing
    """
    def __init__(self, *args, **kwargs):
        """
        init the instance
        """
        super().__init__(*args, **kwargs)

        self.api('libs.api:add')('get:best:match', self.get_best_match)

        self.dependencies = []
        #self.dependencies = ['core.errors', 'core.msg']

    # get the best match for a string in a list of strings
    def get_best_match(self, item_to_match, list_to_match):
        """  get the best match for a string in a list of strings
        @Yitem_to_match@w  = the string to find the closest match for
        @Ylist_to_match@w  = the list of strings to match against

        this function returns:
            a string of the item that best matched or None"""
        found = None
        LogRecord(f"get_best_match - item_to_match: {item_to_match}",
                  level='debug', sources=[self.plugin_id]).send()
        LogRecord(f"get_best_match - list_to_match: {list_to_match}",
                  level='debug', sources=[self.plugin_id]).send()
        matching_startswith = [i for i in list_to_match if i.startswith(item_to_match)]
        if len(matching_startswith) == 1:
            found = matching_startswith[0]
            LogRecord(f"get_best_match (startswith) matched {item_to_match} to {found}",
                      level='debug', sources=[self.plugin_id]).send()
        else:
            sorted_extract = sort_fuzzy_result(process.extract(item_to_match, list_to_match))
            LogRecord(f"get_best_match - extract for {item_to_match} - {sorted_extract}",
                       level='debug', sources=[self.plugin_id]).send()
            maxscore = max(sorted_extract.keys())
            if maxscore > 80 and len(sorted_extract[maxscore]) == 1:
                found = sorted_extract[maxscore][0]
                LogRecord(f"get_best_match - (score) matched {item_to_match} to {found}",
                            level='debug', sources=[self.plugin_id])

        return found
