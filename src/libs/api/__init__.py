# Project: bastproxy
# Filename: libs/api/__init__.py
#
# File Description: holds the api implementation
#
# By: Bast
"""Module for managing API implementations for the bastproxy project.

This module provides the `API` class and `AddAPI` decorator, which handle various API
functionalities within the bastproxy project. It includes methods for managing
API requests, responses, and other related operations.

Key Components:
    - API: A class that handles core API functionalities.
    - AddAPI: A decorator to add a function or method to the API

Features:
    - Management of API requests and responses.
    - Extension of core API functionalities with additional features.

Usage:
    - Instantiate API to handle core API operations.

Classes:
    - `API`: Represents the core API functionalities.

Decorators:
    - `AddAPI`: Extends API to provide additional features.

"""

__all__ = ["API", "AddAPI"]

from ._addapi import AddAPI
from ._api import API
