"""Tests for the bounded zlib decompressor shared by the MUD and client links (#58, #329)."""

import zlib

import pytest

from bastproxy.libs.net.inflate import MAX_INFLATED_CHUNK, BoundedDecompressor


def _compressed(payload: bytes) -> bytes:
    c = zlib.compressobj()
    return c.compress(payload) + c.flush(zlib.Z_SYNC_FLUSH)


def test_output_under_the_limit_is_returned() -> None:
    inflater = BoundedDecompressor(zlib.decompressobj(), 1000)
    assert inflater.decompress(_compressed(b"a" * 999)) == b"a" * 999


def test_output_of_exactly_the_limit_is_returned() -> None:
    inflater = BoundedDecompressor(zlib.decompressobj(), 1000)
    assert inflater.decompress(_compressed(b"a" * 1000)) == b"a" * 1000


def test_output_over_the_limit_raises() -> None:
    inflater = BoundedDecompressor(zlib.decompressobj(), 1000)
    with pytest.raises(zlib.error):
        inflater.decompress(_compressed(b"a" * 1001))


def test_eof_and_unused_data_are_forwarded() -> None:
    inflater = BoundedDecompressor(zlib.decompressobj(), 1000)
    assert inflater.eof is False
    assert inflater.decompress(zlib.compress(b"hi") + b"rest") == b"hi"
    assert inflater.eof is True
    assert inflater.unused_data == b"rest"


def test_default_limit() -> None:
    assert MAX_INFLATED_CHUNK == 16 * 1024 * 1024
