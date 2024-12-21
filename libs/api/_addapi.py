# -*- coding: utf-8 -*-
# Project: bastproxy
# Filename: libs/api/_addapi.py
#
# File Description: hold the decorator to add items to the api
#
# By: Bast
'''Use this decorator to add a function to the api

Example:
    @AddAPI('get.data.directory', description='get the data directory for this plugin')
    def _api_get_data_directory(self):
        """ get the data directory for this plugin """
        return self.plugin_info.data_directory

'''
# Standard Library

# Third Party

# Project


class AddAPI:
    """A decorator class that attaches metadata to functions to create API endpoints.

    This class allows users to annotate functions with an API name and description.
    The API can be bound to an API instance or to a the Global API.
    The metadata can be accessed later for documentation or management tasks.

    Args:
        api (str): The name of the API.
        description (str, optional): A brief description of the API. Defaults to an empty string.
        instance (bool, optional): Indicates if the API needs to be bound to the instance.
                                        Defaults to False.

    Examples:
        @AddAPI('my_api', 'This is my API', instance=True)
        def my_function():
            pass

    """

    def __init__(self, api: str, description="", instance=False):
        """This constructor sets up the API name, an optional description,
        and a flag indicating whether the API should be bound to an instance.

        These attributes are used to annotate functions later when the instance is called as a decorator.

        Args:
            api (str): The name of the API.
            description (str, optional): A brief description of the API. Defaults to an empty string.
            instance (bool, optional): Indicates if the API is an instance method. Defaults to False.

        """
        self.api_name = api
        self.description = description
        self.instance = instance

    def __call__(self, func):
        """Decorates a function by adding API metadata to it.

        This method attaches the API name, description, instance flag,
        and an empty dictionary for additional information to the function being decorated.

        Args:
            func (callable): The function to be decorated with API metadata.

        Returns:
            callable: The original function with the added API metadata.

        """
        func.api = {
            "name": self.api_name,
            "description": self.description,
            "instance": self.instance,
            "addedin": {},
        }

        return func
