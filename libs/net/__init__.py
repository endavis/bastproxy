"""
module with network code
"""
# update telnetlib3 with mud protocols
import telnetlib3.telopt
from libs.records import LogRecord


mud_protocols = {
    'MSSP': bytes([70]),
    'MSDP': bytes([69]),
    'MCCP_COMPRESS': bytes([85]),
    'MCCP2_COMPRESS': bytes([86]),
    'MXP': bytes([91]),
    'MSP': bytes([90]),
    'A102': bytes([102]), # Aardwolf 102
    'ATCP': bytes([200]), # Achaea 200
    'GMCP': bytes([201]),
}

for item in mud_protocols:
    if not hasattr(telnetlib3.telopt, item):
        LogRecord(f"Adding {item} to telnetlib3.telopt", level='debug', sources=[__name__])()
        setattr(telnetlib3.telopt, item, mud_protocols[item])
        telnetlib3.telopt._DEBUG_OPTS[mud_protocols[item]] = item # type: ignore
