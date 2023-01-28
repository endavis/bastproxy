# -*- coding: utf-8 -*-
# Project: bastproxy
# Filename: libs/log.py
#
# File Description: setup logging with some customizations
#
# By: Bast/Jubelo
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
from libs.api import API

default_log_file = "bastproxy.log"
data_logger_log_file = "networkdata.log"

def setup_loggers(log_level):

    default_log_file_path = API.BASEDATALOGPATH / default_log_file
    os.makedirs(API.BASEDATALOGPATH / 'networkdata', exist_ok=True)
    data_logger_log_file_path = API.BASEDATALOGPATH / 'networkdata' / data_logger_log_file

    # This code sets up a logger with a default log level of log_level, and attaches a
    # default file handler to it.  The default file handler will log to the file
    # "default_log_file", and will overwrite any existing contents.  It will also
    # log to stdout with a level of log_level.
    logging.basicConfig(
        format="%(asctime)s: %(name)-10s - %(levelname)-9s - %(message)s",
        filename=default_log_file_path,
        filemode='w',
        level=log_level)

    # Create a console handler with a log level of log_level
    console = logging.StreamHandler()
    console.formatter = logging.Formatter("%(asctime)s " + API.TIMEZONE + " : %(name)-10s - %(levelname)-9s - %(message)s")
    console.setLevel(log_level)
    # add the handler to the root logger
    logging.getLogger().addHandler(console)

    # This logger is for any network data from both the mud and the client to facilitate
    # debugging. It is not intended to be used for general logging.
    # This code creates a logger object named data, sets the log level to
    # INFO, and sets the format of the log message. It also creates a file handler
    # and adds it to the logger object. The file handler rotates the log file at
    # midnight. Finally, it disables propagation of log messages to the root
    # logger.
    # logging network data from the mud will use data.mud
    # logging network data from the client will use data.client
    data_logger = logging.getLogger("data")
    data_logger.setLevel(logging.INFO)
    data_logger_file_handler = logging.handlers.TimedRotatingFileHandler(data_logger_log_file_path, when='midnight')
    data_logger_file_handler.formatter = logging.Formatter("%(asctime)s " + API.TIMEZONE + " : %(name)-11s - %(message)s")
    data_logger.addHandler(data_logger_file_handler)
    data_logger.propagate = False

    logging.getLogger("data.mud").info('Testing logging for data from the mud')
    logging.getLogger("data.client").info('Testing logging for data from the client')