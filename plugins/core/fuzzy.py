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
    import rapidfuzz
except ImportError:
    print('Please install required libraries. fuzzywuzzy is missing.')
    print('From the root of the project: pip(3) install -r requirements.txt')
    sys.exit(1)

# Project
from plugins._baseplugin import BasePlugin
from libs.records import LogRecord

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
        if i[1] not in newdict:
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

        self.api('libs.api:add')(self.plugin_id, 'get.best.match', self._api_get_best_match)
        self.api('libs.api:add')(self.plugin_id, 'get.top.matches', self._api_get_top_matches)

    # get the best match for a string in a list of strings
    def _api_get_best_match(self, item_to_match, list_to_match, score_cutoff = 80,
                       scorer: str = 'ratio') -> str:
        """  get the best match for a string in a list of strings
        @Yitem_to_match@w  = the string to find the closest match for
        @Ylist_to_match@w  = the list of strings to match against

        scorer can be ratio, partial_ratio, token_sort_ratio,
                token_set_ratio, partial_token_sort_ratio,
                partial_token_set_ratio

        this function returns:
            a string of the item that best matched or None"""
        found = ''
        scorer_inst = rapidfuzz.fuzz.__dict__[scorer]
        LogRecord(f"_api_get_best_match - {item_to_match=}, {scorer=} {score_cutoff=}",
                  level='debug', sources=[self.plugin_id])()
        LogRecord(f"_api_get_best_match - {list_to_match=}",
                  level='debug', sources=[self.plugin_id])()
        if item_to_match in list_to_match:
            found = item_to_match
            LogRecord(f"_api_get_best_match (exact) matched {item_to_match} to {found}",
                      level='debug', sources=[self.plugin_id])()
        else:
            matching_startswith = [i for i in list_to_match if i.startswith(item_to_match)]
            if len(matching_startswith) == 1:
                found = matching_startswith[0]
                LogRecord(f"_api_get_best_match (startswith) matched {item_to_match} to {found}",
                        level='debug', sources=[self.plugin_id])()
            else:
                sorted_extract = sort_fuzzy_result(rapidfuzz.process.extract(item_to_match, list_to_match, scorer=scorer_inst))
                LogRecord(f"_api_get_best_match - extract for {item_to_match} - {sorted_extract}",
                        level='debug', sources=[self.plugin_id])()
                maxscore = max(sorted_extract.keys())
                if maxscore > score_cutoff and len(sorted_extract[maxscore]) == 1:
                    found = sorted_extract[maxscore][0]
                    LogRecord(f"_api_get_best_match - (score) matched {item_to_match} to {found}",
                                level='debug', sources=[self.plugin_id])

        return found

    def _api_get_top_matches(self, item_to_match, list_to_match, items=5, score_cutoff=80, scorer: str = 'ratio') -> list:
        """
        scorer can be ratio, partial_ratio, token_sort_ratio,
                        token_set_ratio, partial_token_sort_ratio,
                        partial_token_set_ratio

        get the top fuzzy matches for a string
        """
        scorer_inst = rapidfuzz.fuzz.__dict__[scorer]
        found = []

        LogRecord(f"_api_get_top_matches - {item_to_match =} {items =} {score_cutoff =}",
                  level='debug', sources=[self.plugin_id])()
        LogRecord(f"_api_get_top_matches - list_to_match: {list_to_match}",
                  level='debug', sources=[self.plugin_id])()

        extract = rapidfuzz.process.extract(item_to_match, list_to_match, scorer=scorer_inst, limit=items)
        sorted_extract = sort_fuzzy_result(extract)

        LogRecord(f"__api_get_top_matches - extract for {item_to_match} - {sorted_extract}",
                    level='debug', sources=[self.plugin_id])()
        for i in sorted(sorted_extract.keys(), reverse=True):
            if i > score_cutoff:
                found.extend(sorted_extract[i])
            if len(found) >= items:
                break

        LogRecord(f"_api_get_top_matches - (score) matched {item_to_match} to {found}",
                    level='debug', sources=[self.plugin_id])

        return found