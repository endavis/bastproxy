# Project: bastproxy
# Filename: plugins/core/fuzzy/_fuzzy.py
#
# File Description: a plugin to do fuzzy matching with strings
#
# By: Bast

# Standard Library
import sys
from functools import lru_cache

# 3rd Party
try:
    import rapidfuzz
except ImportError:
    print("Please install required libraries. fuzzywuzzy is missing.")
    print("From the root of the project: uv sync --all-extras")
    sys.exit(1)

# Project
from bastproxy.libs.api import AddAPI
from bastproxy.libs.logger import get_logger
from bastproxy.plugins._baseplugin import BasePlugin


def sort_fuzzy_result(result):
    """Sort a result from extract."""
    newdict = {}
    for i in result:
        if i[1] not in newdict:
            newdict[i[1]] = []
        newdict[i[1]].append(i[0])
    return newdict


class FuzzyPlugin(BasePlugin):
    """a plugin to test command parsing."""

    @lru_cache(maxsize=128)
    @AddAPI(
        "string.match.best",
        description="get the best match for a string in a list of strings",
    )
    def _api_string_match_best(
        self,
        item_to_match,
        list_to_match: tuple,
        score_cutoff=80,
        scorer: str = "ratio",
    ) -> str:
        """Get the best match for a string in a list of strings.

        @Yitem_to_match@w  = the string to find the closest match for
        @Ylist_to_match@w  = the list of strings to match against.

        scorer can be ratio, partial_ratio, token_sort_ratio,
                token_set_ratio, partial_token_sort_ratio,
                partial_token_set_ratio

        this function returns:
            a string of the item that best matched or None
        """
        found = ""
        scorer_inst = rapidfuzz.fuzz.__dict__[scorer]
        get_logger(self.plugin_id).debug(
            "_api_string_match_best - item_to_match=%r, scorer=%r score_cutoff=%r",
            item_to_match,
            scorer,
            score_cutoff,
        )
        get_logger(self.plugin_id).debug("_api_string_match_best - list_to_match=%r", list_to_match)

        if item_to_match in list_to_match:
            get_logger(self.plugin_id).debug(
                "_api_string_match_best (exact) matched %s to %s", item_to_match, found
            )
            return item_to_match

        matching_startswith = [i for i in list_to_match if i.startswith(item_to_match)]
        if len(matching_startswith) == 1:
            found = matching_startswith[0]
            get_logger(self.plugin_id).debug(
                "_api_string_match_best (startswith) matched %s to %s", item_to_match, found
            )
        else:
            sorted_extract = sort_fuzzy_result(
                rapidfuzz.process.extract(item_to_match, list_to_match, scorer=scorer_inst)
            )
            get_logger(self.plugin_id).debug(
                "_api_string_match_best - extract for %s - %s", item_to_match, sorted_extract
            )
            maxscore = max(sorted_extract.keys())
            if maxscore > score_cutoff and len(sorted_extract[maxscore]) == 1:
                found = sorted_extract[maxscore][0]
                get_logger(self.plugin_id).debug(
                    "_api_string_match_best - (score) matched %s to %s", item_to_match, found
                )

        return found

    @lru_cache(maxsize=128)
    @AddAPI("string.match.top", description="get the top fuzzy matches for a string")
    def _api_string_match_top(
        self,
        item_to_match,
        list_to_match: tuple,
        items=5,
        score_cutoff=80,
        scorer: str = "ratio",
    ) -> list:
        """Scorer can be ratio, partial_ratio, token_sort_ratio,.

                        token_set_ratio, partial_token_sort_ratio,
                        partial_token_set_ratio.

        get the top fuzzy matches for a string
        """
        scorer_inst = rapidfuzz.fuzz.__dict__[scorer]
        found = []

        get_logger(self.plugin_id).debug(
            "_api_string_match_top - item_to_match =%r items =%r score_cutoff =%r",
            item_to_match,
            items,
            score_cutoff,
        )
        get_logger(self.plugin_id).debug("_api_string_match_top - list_to_match: %s", list_to_match)

        extract = rapidfuzz.process.extract(
            item_to_match, list_to_match, scorer=scorer_inst, limit=items
        )
        sorted_extract = sort_fuzzy_result(extract)

        get_logger(self.plugin_id).debug(
            "_api_string_match_top - extract for %s - %s", item_to_match, sorted_extract
        )
        for i in sorted(sorted_extract.keys(), reverse=True):
            if i > score_cutoff:
                found.extend(sorted_extract[i])
            if len(found) >= items:
                break

        get_logger(self.plugin_id).debug(
            "_api_string_match_top - (score) matched %s to %s", item_to_match, found
        )

        return found
