# -*- coding: utf-8 -*-
# Project: bastproxy
# Filename: libs/log.py
#
# File Description: setup logging with some customizations
#
# By: Bast
"""
This plugin sets up logging for various types of data

data from the mud and the client
general logging of everything else which will use the root logger
"""

# Standard Library
import os
import logging
import logging.handlers

# Third Party

# Project

default_log_file = "bastproxy.log"
data_logger_log_file = "networkdata.log"

def setup_loggers(log_level):

    from libs.api import API

    logging.getLogger().setLevel(log_level)

    default_log_file_path = API.BASEDATALOGPATH / default_log_file
    os.makedirs(API.BASEDATALOGPATH / 'networkdata', exist_ok=True)
    data_logger_log_file_path = API.BASEDATALOGPATH / 'networkdata' / data_logger_log_file

    # This logger is the root logger and will be setup with log_level from
    # a command line argument. It will log to a file and to the console.
    file_handler = logging.handlers.TimedRotatingFileHandler(filename=default_log_file_path,
                                                    when='midnight')
    file_handler.formatter = logging.Formatter("%(asctime)s " + API.TIMEZONE + " : %(name)-12s - %(levelname)-9s - %(message)s")

    # add the handler to the root logger
    logging.getLogger().addHandler(file_handler)

    # This logger is for any network data from both the mud and the client to facilitate
    # debugging. It is not intended to be used for general logging. It will not use the same
    # log settings as the root logger. It will log to a file and not to the console.
    # logging network data from the mud will use data.mud
    # logging network data to/from the client will use data.<client_uuid>
    data_logger = logging.getLogger("data")
    data_logger.setLevel(logging.INFO)
    data_logger_file_handler = logging.handlers.TimedRotatingFileHandler(data_logger_log_file_path, when='midnight')
    data_logger_file_handler.formatter = logging.Formatter("%(asctime)s " + API.TIMEZONE + " : %(name)-11s - %(message)s")
    data_logger.addHandler(data_logger_file_handler)
    data_logger.propagate = False
