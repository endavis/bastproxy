# Project: bastproxy
# Filename: plugins/core/fuzzy/_fuzzy.py
#
# File Description: a plugin to do fuzzy matching with strings
#
# By: Bast

# Standard Library
import sys
from functools import lru_cache
from typing import Any

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


def sort_fuzzy_result(result: Any) -> dict[Any, list[Any]]:
    """Sort a result from extract."""
    newdict: dict[Any, list[Any]] = {}
    for i in result:
        if i[1] not in newdict:
            newdict[i[1]] = []
        newdict[i[1]].append(i[0])
    return newdict


_LOGGER_NAME = "plugins.core.fuzzy"


@lru_cache(maxsize=128)
def _match_best(item_to_match: str, list_to_match: tuple, score_cutoff: float, scorer: str) -> str:
    """Find the best match for a string; cached without holding a plugin instance."""
    logger = get_logger(_LOGGER_NAME)
    found = ""
    scorer_inst = rapidfuzz.fuzz.__dict__[scorer]
    logger.debug(
        "_api_string_match_best - item_to_match=%r, scorer=%r score_cutoff=%r",
        item_to_match,
        scorer,
        score_cutoff,
    )
    logger.debug("_api_string_match_best - list_to_match=%r", list_to_match)

    if item_to_match in list_to_match:
        logger.debug("_api_string_match_best (exact) matched %s to %s", item_to_match, found)
        return item_to_match

    matching_startswith = [i for i in list_to_match if i.startswith(item_to_match)]
    if len(matching_startswith) == 1:
        found = matching_startswith[0]
        logger.debug("_api_string_match_best (startswith) matched %s to %s", item_to_match, found)
    else:
        sorted_extract = sort_fuzzy_result(
            rapidfuzz.process.extract(item_to_match, list_to_match, scorer=scorer_inst)
        )
        logger.debug("_api_string_match_best - extract for %s - %s", item_to_match, sorted_extract)
        maxscore = max(sorted_extract.keys())
        if maxscore > score_cutoff and len(sorted_extract[maxscore]) == 1:
            found = sorted_extract[maxscore][0]
            logger.debug("_api_string_match_best - (score) matched %s to %s", item_to_match, found)

    return found


@lru_cache(maxsize=128)
def _match_top(
    item_to_match: str, list_to_match: tuple, items: int, score_cutoff: float, scorer: str
) -> tuple:
    """Find the top matches for a string; returns a tuple so the cache stays immutable."""
    logger = get_logger(_LOGGER_NAME)
    scorer_inst = rapidfuzz.fuzz.__dict__[scorer]
    found: list = []

    logger.debug(
        "_api_string_match_top - item_to_match =%r items =%r score_cutoff =%r",
        item_to_match,
        items,
        score_cutoff,
    )
    logger.debug("_api_string_match_top - list_to_match: %s", list_to_match)

    extract = rapidfuzz.process.extract(
        item_to_match, list_to_match, scorer=scorer_inst, limit=items
    )
    sorted_extract = sort_fuzzy_result(extract)

    logger.debug("_api_string_match_top - extract for %s - %s", item_to_match, sorted_extract)
    for i in sorted(sorted_extract.keys(), reverse=True):
        if i > score_cutoff:
            found.extend(sorted_extract[i])
        if len(found) >= items:
            break

    logger.debug("_api_string_match_top - (score) matched %s to %s", item_to_match, found)

    return tuple(found)


class FuzzyPlugin(BasePlugin):
    """a plugin to test command parsing."""

    @AddAPI(
        "string.match.best",
        description="get the best match for a string in a list of strings",
    )
    def _api_string_match_best(
        self,
        item_to_match: str,
        list_to_match: tuple,
        score_cutoff: float = 80,
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
        return _match_best(item_to_match, list_to_match, score_cutoff, scorer)

    @AddAPI("string.match.top", description="get the top fuzzy matches for a string")
    def _api_string_match_top(
        self,
        item_to_match: str,
        list_to_match: tuple,
        items: int = 5,
        score_cutoff: float = 80,
        scorer: str = "ratio",
    ) -> list:
        """Scorer can be ratio, partial_ratio, token_sort_ratio,.

                        token_set_ratio, partial_token_sort_ratio,
                        partial_token_set_ratio.

        get the top fuzzy matches for a string
        """
        return list(_match_top(item_to_match, list_to_match, items, score_cutoff, scorer))
