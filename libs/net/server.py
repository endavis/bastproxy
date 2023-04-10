# -*- coding: utf-8 -*-
# Project: bastproxy
# Filename: libs/net/server.py
#
# File Description: creates the server for the proxy
#
# By: Bast
# Standard Library
import sys

# 3rd Party
try:
    import telnetlib3
except ImportError:
    print('Please install required libraries. telnetlib3 is missing.')
    print('From the root of the project: pip(3) install -r requirements.txt')
    sys.exit(1)

# Project

class CustomTelnetServer(telnetlib3.TelnetServer):

    def begin_advanced_negotiation(self):
        from telnetlib3 import DO, NEW_ENVIRON, NAWS, CHARSET

        if self.writer:
            self.writer.iac(DO, NEW_ENVIRON)
            self.writer.iac(DO, NAWS)
            if self.default_encoding:
                self.writer.iac(DO, CHARSET)

def create_server(*args, **kwargs):
    kwargs['protocol_factory'] = CustomTelnetServer
    return telnetlib3.create_server(*args, **kwargs)