"""Tests that client-bound line endings are CRLF (``\\r\\n``), not ``\\n\\r`` (#69)."""

from bastproxy.libs.records.rtypes.networkdata import NetworkDataLine


def test_network_data_line_ends_with_crlf() -> None:
    line = NetworkDataLine("hello", originated="mud")
    line.add_line_endings()
    assert line.line == "hello\r\n"


def test_network_data_line_without_line_endings_unchanged() -> None:
    line = NetworkDataLine("hello", originated="mud", had_line_endings=False)
    line.add_line_endings()
    assert line.line == "hello"
