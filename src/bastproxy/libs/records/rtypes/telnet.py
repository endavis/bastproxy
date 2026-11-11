# Project: bastproxy
# Filename: libs/records/rtypes/telnet.py
#
# File Description: Holds the records for telnet negotiation and protocol messages
#
# By: Bast
"""Holds the telnet negotiation and protocol message records.

Both are data records: they do not start a retention root, so a parentless one is a pending
record under ``MAX_PENDING``, and one created while a processing record is active joins its tree.
"""

# Standard Library
from typing import Any, ClassVar

# 3rd Party
# Project
from bastproxy.libs.records.enums import Direction, UpdateFlag
from bastproxy.libs.records.rtypes.base import BaseRecord

__all__ = ["TelnetNegotiation", "TelnetProtocolMessage"]


class TelnetRecord(BaseRecord):
    """The base of the telnet records: a direction and the link it travelled on."""

    retention_root: ClassVar[bool] = False

    def __init__(
        self,
        direction: Direction | str,
        link: str,
        owner_id: str = "",
        parent: Any = None,
    ) -> None:
        """Initialize the record.

        Args:
            direction: A ``Direction`` or its string.
            link: The link id: ``"mud"`` or the uuid of a client link.
            owner_id: The owner id, the class name when empty.
            parent: The parent record, the latest active record when None.

        Raises:
            ValueError: If ``direction`` is not a ``Direction``.

        """
        # Coerce first so a bad value never registers a half-built record.
        direction = Direction(direction)
        super().__init__(owner_id=owner_id, parent=parent)
        self.direction: Direction = direction
        self.link: str = link

    def get_attributes_to_format(self) -> dict[int, list[tuple[str, Any]]]:
        """Add the direction and link to the detail view."""
        attributes = super().get_attributes_to_format()
        attributes[0].extend([("Direction", "direction"), ("Link", "link")])
        return attributes


class TelnetNegotiation(TelnetRecord):
    """One telnet option negotiation: DO, DONT, WILL, WONT or SB."""

    def __init__(
        self,
        command: str,
        option: str,
        direction: Direction | str,
        link: str,
        data: bytes = b"",
        raw: bytes = b"",
        owner_id: str = "",
        parent: Any = None,
    ) -> None:
        """Initialize the record.

        Args:
            command: The command name: DO, DONT, WILL, WONT or SB.
            option: The option name, such as TTYPE.
            direction: A ``Direction`` or its string.
            link: The link id: ``"mud"`` or the uuid of a client link.
            data: The subnegotiation payload after the option, IAC IAC unescaped.
            raw: The IAC sequence as it travelled.
            owner_id: The owner id, the class name when empty.
            parent: The parent record, the latest active record when None.

        """
        super().__init__(direction, link, owner_id=owner_id, parent=parent)
        self.command = command
        self.option = option
        self.data = data
        self.raw = raw
        self.addupdate(UpdateFlag.INFO, f"{self.command} {self.option} {self.direction}")

    def get_attributes_to_format(self) -> dict[int, list[tuple[str, Any]]]:
        """Add the command, option, data and raw bytes to the detail view."""
        attributes = super().get_attributes_to_format()
        attributes[0].extend(
            [("Command", "command"), ("Option", "option"), ("Data", "data"), ("Raw", "raw")]
        )
        return attributes

    def one_line_summary(self) -> str:
        """Get a one line summary of the record."""
        return (
            f"{self.__class__.__name__:<20} {self.uuid} {self.link} "
            f"{self.direction} {self.command} {self.option}"
        )


class TelnetProtocolMessage(TelnetRecord):
    """One decoded protocol message such as GMCP, MSDP or MSSP.

    Only the shape lives here. ``libs/net/protocols.py`` creates the GMCP and MSDP instances (#59);
    the other protocol issues create theirs.
    """

    def __init__(
        self,
        protocol: str,
        package: str,
        data: Any,
        direction: Direction | str,
        link: str,
        owner_id: str = "",
        parent: Any = None,
    ) -> None:
        """Initialize the record.

        Args:
            protocol: The protocol name, such as GMCP.
            package: The package or variable name, such as ``Char.Vitals``.
            data: The decoded payload.
            direction: A ``Direction`` or its string.
            link: The link id: ``"mud"`` or the uuid of a client link.
            owner_id: The owner id, the class name when empty.
            parent: The parent record, the latest active record when None.

        """
        super().__init__(direction, link, owner_id=owner_id, parent=parent)
        self.protocol = protocol
        self.package = package
        self.data = data
        self.addupdate(UpdateFlag.INFO, f"{self.protocol} {self.package} {self.direction}")

    def get_attributes_to_format(self) -> dict[int, list[tuple[str, Any]]]:
        """Add the protocol, package and data to the detail view."""
        attributes = super().get_attributes_to_format()
        attributes[0].extend([("Protocol", "protocol"), ("Package", "package"), ("Data", "data")])
        return attributes

    def one_line_summary(self) -> str:
        """Get a one line summary of the record."""
        return (
            f"{self.__class__.__name__:<20} {self.uuid} {self.link} "
            f"{self.direction} {self.protocol} {self.package}"
        )
