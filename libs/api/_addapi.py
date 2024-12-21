# -*- coding: utf-8 -*-
# Project: bastproxy
# Filename: libs/api/_addapi.py
#
# File Description: hold the decorator to add items to the api
#
# By: Bast
"""Module for adding API metadata to functions using a decorator.

This module provides the `AddAPI` class, which allows users to annotate functions
with API metadata, including the API name, description, and instance flag. This
metadata can be used for documentation or management tasks, making it easier to
track and manage API endpoints within an application.

Key Components:
    - AddAPI: A decorator class that attaches metadata to functions to create API
        endpoints.

Features:
    - Annotate functions with API name, description, and instance flag.
    - Access API metadata for documentation or management tasks.
    - Bind API metadata to instance methods if needed.

Usage:
    - Use the `AddAPI` decorator to annotate functions with API metadata.
    - Access the metadata through the decorated function's attributes.

Classes:
    - `AddAPI`: Represents a decorator class that attaches metadata to functions.

"""
# Standard Library
from typing import Callable

# Third Party

# Project


class AddAPI:
    """Decorator class for attaching API metadata to functions.

    This class allows users to annotate functions with metadata such as the API name,
    description, and instance flag. The metadata can be used for documentation or
    management tasks, making it easier to track and manage API endpoints within an
    application.

    """

    def __init__(self, api: str, description: str = "", instance: bool = False) -> None:
        """Initialize the AddAPI decorator with metadata.

        This method initializes the decorator with the provided API name, description,
        and instance flag. These values are stored as attributes of the decorator
        instance and will be attached to the decorated function.

        Args:
            api: The name of the API.
            description: A brief description of the API.
            instance: A flag indicating whether the API should be bound to the API
                instance instead of the class.

        """
        self.api_name = api
        self.description = description
        self.instance = instance

    def __call__(self, func: Callable) -> Callable:
        """Attach API metadata to the decorated function.

        This method attaches the API name, description, and instance flag as metadata
        to the decorated function. The metadata is stored in a dictionary and can be
        accessed through the function's `api` attribute.

        Args:
            func: The function to be decorated.

        Returns:
            The decorated function with attached API metadata.

        Raises:
            None

        Example:
            >>> @AddAPI(api="example", description="An example API", instance=True)
            ... def example_function():
            ...     pass
            >>> example_function.api
            {'name': 'example', 'description': 'An example API', 'instance': True,
             'addedin': {}}

        """
        func.api = {  # type: ignore
            "name": self.api_name,
            "description": self.description,
            "instance": self.instance,
            "addedin": {},
        }

        return func
