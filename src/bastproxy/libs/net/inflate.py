# Project: bastproxy
# Filename: libs/net/inflate.py
#
# File Description: a zlib decompressor that limits the output of one call
#
# By: Bast
"""A bounded wrapper around a zlib decompressor, shared by the MUD and client links (#58, #329)."""

# Standard Library
import zlib
from typing import Any

#: Default most bytes one call may inflate to; a link sets its own limit.
MAX_INFLATED_CHUNK = 16 * 1024 * 1024


class BoundedDecompressor:
    """Wrap a zlib decompressor so one call cannot inflate past ``limit``.

    An over-limit chunk raises ``zlib.error``, which the callers treat as a broken stream.
    """

    def __init__(self, inner: Any, limit: int = MAX_INFLATED_CHUNK) -> None:
        """Wrap *inner*, a ``zlib.decompressobj`` result, with an output limit of *limit* bytes."""
        self._inner = inner
        self._limit = limit

    def decompress(self, data: bytes) -> bytes:
        """Inflate *data*, raising ``zlib.error`` when the output exceeds the limit."""
        out: bytes = self._inner.decompress(data, self._limit + 1)
        if len(out) > self._limit or self._inner.unconsumed_tail:
            raise zlib.error("chunk exceeded the inflation limit")
        return out

    def __getattr__(self, name: str) -> Any:
        """Forward ``eof``, ``unused_data`` and the rest to the wrapped decompressor."""
        return getattr(self._inner, name)
