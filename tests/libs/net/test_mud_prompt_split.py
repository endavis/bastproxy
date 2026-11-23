"""A prompt ended by IAC GA or IAC EOR is its own line, however the bytes arrive (#735)."""

import asyncio

import pytest
from telnetlib3.telopt import CMD_EOR, GA, IAC

from bastproxy.libs.net.mud import MudLine

from .test_mud_connection import TIMEOUT, _connect, _read, raw_server

PROMPT = "[160/160hp 135/135mn 550/550mv 0qt 821tnl] > *[NOEXP]* "
REPLY = "You are not currently on a campaign."
PROMPT_B = PROMPT.encode()
REPLY_B = REPLY.encode()
CRLF = b"\r\n"

PROMPT_LINE = MudLine(PROMPT, False, True)
REPLY_LINE = MudLine(REPLY + "\r\n", True, False)
BLANK_LINE = MudLine("\r\n", True, False)
SPLIT = [PROMPT_LINE, REPLY_LINE]

# (id, chunks, expected lines). A pause separates chunks, so each is its own packet.
CASES = [
    ("one-chunk-ga", [PROMPT_B + IAC + GA + REPLY_B + CRLF], SPLIT),
    ("one-chunk-eor", [PROMPT_B + IAC + CMD_EOR + REPLY_B + CRLF], SPLIT),
    (
        "one-chunk-ga-crlf-before",
        [CRLF + PROMPT_B + IAC + GA + REPLY_B + CRLF],
        [BLANK_LINE, *SPLIT],
    ),
    ("ga-at-chunk-end", [PROMPT_B + IAC + GA, REPLY_B + CRLF], SPLIT),
    ("prompt-then-ga-chunk", [PROMPT_B, IAC + GA + REPLY_B + CRLF], SPLIT),
    (
        "text-split-across-chunks",
        [PROMPT_B[:20], PROMPT_B[20:] + IAC + GA + REPLY_B[:10], REPLY_B[10:] + CRLF],
        SPLIT,
    ),
    ("ga-split-in-iac", [PROMPT_B + IAC, GA + REPLY_B + CRLF], SPLIT),
]


@pytest.mark.parametrize(("chunks", "expected"), [c[1:] for c in CASES], ids=[c[0] for c in CASES])
async def test_prompt_and_following_text_are_separate_lines(
    chunks: list[bytes], expected: list[MudLine]
) -> None:
    done = asyncio.Event()

    async def handler(_r: asyncio.StreamReader, w: asyncio.StreamWriter) -> None:
        for chunk in chunks:
            w.write(chunk)
            await w.drain()
            await asyncio.sleep(0.02)
        await asyncio.wait_for(done.wait(), TIMEOUT)
        w.close()

    async with raw_server(handler) as port:
        reader, writer = await _connect(port)
        reader.line_timeout = 5
        lines = [await _read(reader) for _ in expected]
        assert lines == expected
        done.set()
        writer.close()
