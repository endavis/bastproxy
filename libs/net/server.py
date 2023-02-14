import telnetlib3

class CustomTelnetServer(telnetlib3.TelnetServer):

    def begin_advanced_negotiation(self):
        from telnetlib3 import DO, WILL, SGA, ECHO, BINARY, NEW_ENVIRON, NAWS, CHARSET

        self.writer.iac(DO, NEW_ENVIRON)
        self.writer.iac(DO, NAWS)
        if self.default_encoding:
            self.writer.iac(DO, CHARSET)

def create_server(*args, **kwargs):
    kwargs['protocol_factory'] = CustomTelnetServer
    return telnetlib3.create_server(*args, **kwargs)