---
title: Network Layer Analysis and Findings
description: Audit of the network layer and its use of telnetlib3 - private API, deprecations, reimplemented features, patches, the 5.0.2 release, test coverage, the status of the open network issues and patterns, with defects and a patterns review
audience:
  - contributors
  - ai-agents
tags:
  - architecture
  - networking
  - review
---

# Network Layer Analysis and Findings

**Date:** 2026-11-10
**Analyzer:** Claude Sonnet 5.5
**Scope:** The network layer in `src/bastproxy/libs/net/` (`__init__.py`, `client.py`, `listeners.py`,
`mud.py`, `server.py`, `telnet.py`) and how it uses telnetlib3: private API, deprecated API, features the
proxy reimplements, patches, the 5.0.2 release, test coverage, the status of the open network issues, and
patterns (audit issue #304). Compared against [Data Flow](data_flow.md) and
[ADR-0001](../decisions/0001-terminate-mud-telnet-protocols-at-the-proxy.md). Base commit `c9bb559`,
telnetlib3 5.0.1 (the version `uv.lock` pins).

This audit filed #305 to #311, one issue per defect or change; they are listed in
[New Defects and Changes](#new-defects-and-changes). Corrections to #66, #67, #90 and #272 are posted as
comments on those issues.

## Table of Contents

1. [Executive Summary](#executive-summary)
2. [How This Was Verified](#how-this-was-verified)
3. [Q1: Which telnetlib3 Private API Does the Proxy Use?](#q1-which-telnetlib3-private-api-does-the-proxy-use)
4. [Q2: Does the Proxy Call Deprecated API?](#q2-does-the-proxy-call-deprecated-api)
5. [Q3: What Does the Proxy Reimplement?](#q3-what-does-the-proxy-reimplement)
6. [Q4: Every Patch, Override and setattr](#q4-every-patch-override-and-setattr)
7. [Q5: What Changed in 5.0.2?](#q5-what-changed-in-502)
8. [Q6: What Is Untested?](#q6-what-is-untested)
9. [Q7: Do the Existing Issues Still Hold?](#q7-do-the-existing-issues-still-hold)
10. [Q8: Patterns and Anti-Patterns](#q8-patterns-and-anti-patterns)
11. [New Defects and Changes](#new-defects-and-changes)
12. [Other Observations](#other-observations)

---

## Executive Summary

The network layer works for the common case: a live session against Evennia 6.1.0 connects, relays the
welcome screen and `look`, and runs under `PYTHONWARNINGS=error::DeprecationWarning` with no warning
(Q2, **verified**). Its use of telnetlib3 is narrow and mostly public. The private surface is one class,
`MudTelnetReader`, plus one module patch, and a canary test already guards the class. What the audit found
is three defects, one feature gap, three housekeeping items and a set of stale claims in open issues.

- **Private API is small and guarded** (Q1). Five private reader names, one private client class attribute
  and one private module dict. None of them changed in 5.0.2. `test_reader_wiring_and_protected_names_exist`
  asserts that the five reader names and the factory attribute exist.
- **No deprecated telnetlib3 API is called** (Q2, **verified**). `tests/libs/net` passes with
  `-W error::DeprecationWarning`, and a live session logs no warning. The only deprecation the run turned up
  is pytest-asyncio's, about an unset config option (#310).
- **The `telopt` patch is not needed** (Q4, **verified**). telnetlib3 5.0.1 defines all nine options. Eight have the
  proxy's names; the ninth, `A102`, is telnetlib3's `AARDWOLF` (byte 102). The patch only renames
  telnetlib3's own `_DEBUG_OPTS[102]` from `AARDWOLF` to `A102` at import. Issue #67 as filed said "8 of 9" and keeping `A102`; the
  audit corrected this, and #67 deleted the whole patch. **Status:** fixed by #67; the whole patch is deleted.
- **A client that sends invalid UTF-8 is disconnected** (Q8, **verified**, #305). The listeners keep
  telnetlib3's server default `encoding_errors="strict"`, and `client_read` catches only `ConnectionError`.
  **Status:** fixed by #305 (`encoding_errors="replace"` on both listeners; `client_read` also ends cleanly on `UnicodeDecodeError`).
- **Client echo and the empty `begin_advanced_negotiation` bypass telnetlib3's option state** (Q3, Q4 #3, **verified**, #66).
  **Status:** fixed by #66. Echo goes through `writer.iac(WILL, ECHO)` and `writer.iac(WONT, ECHO)`, so each is sent once. The override sends `DO NAWS` and `WILL BINARY`, keeps `WILL SGA` off (GA, #272) and does not request CHARSET or MCCP. `ClientConnection.rows`/`cols` read the NAWS size from the writer; `echo_on` and `echo_off` had no callers left and were removed by #67.
- **A failed MUD connect leaves the proxy believing it is connected** (Q8, **verified**, #306).
  `MudConnection.connected` starts `True`; after a refused connection `#bp.core.proxy.connect` answers "currently
  connected" and never retries.
  **Status:** fixed by #306. `MudConnection.connected` starts `False`, becomes `True` when the connection opens, and
  `connect_to_mud` reports a failed connect to the client.
- **The Clients table shows the literal text "Term Type"** (Q3, **verified**, #307), although
  telnetlib3 records the client's terminal type. **Status:** fixed by #307; `ClientConnection.term_type`
  reads `writer.get_extra_info("TERM")` and the table shows `-` until the client answers TTYPE (or if it never does). The property keeps only letters, digits and `._+-`, capped at 32 characters.
- **#272 does not hold as written** (Q7, **verified**). `CustomTelnetServer` never sends `WILL SGA`, so
  `send_ga()` does send GA to clients. #90's `assert` caveat is also stale: `idle` does not raise before
  the first byte. #66 and #67 hold with corrections.
- **The proxy reimplements little that telnetlib3 provides** (Q3). Echo, idle time and the client's terminal
  data are the real switches; line handling is a justified reimplementation with no public alternative; the
  MUD protocol handlers belong to #58 to #61.
- **5.0.2 changes only `TelnetReaderUnicode` end-of-stream decoding** (Q5, **verified** by diff). It does not
  change `MudTelnetReader`. It makes the client-side `readline()` raise `UnicodeDecodeError` for a truncated
  trailing character, which `client_read` does not catch (#305 covers it; #311 moves the floor).
- **Coverage of `src/bastproxy/libs/net/` is 47.61%** (Q6, **verified**). `CustomTelnetServer`, `Listeners.check_listeners_available`,
  the login path, `setup_client` and `mud_write` have no test.

---

## How This Was Verified

Claims are tagged **verified** (run against the code, output pasted), **read** (from reading the code, not
executed) or **unverified**. Measurements ran in the `chore/304-network-audit` worktree with
`BASTPROXY_HOME` set to a scratch directory. Scripts were throwaway and are not part of the repository.

- telnetlib3 facts come from the installed 5.0.1 package under `.venv/lib/python3.12/site-packages/telnetlib3/`.
- 5.0.2 was downloaded with `pip download telnetlib3==5.0.2 --no-deps`, unpacked into a scratch directory
  and diffed against the 5.0.1 wheel. `pyproject.toml` and `uv.lock` were not changed. The 5.0.2 behaviour
  checks put that directory first on `sys.path` or `PYTHONPATH`.
- Q2: `uv run pytest tests/libs/net -W error::DeprecationWarning ...`, a grep of the installed package for
  `warnings.warn` and `deprecat`, and a live proxy run with `PYTHONWARNINGS=error::DeprecationWarning`.
- Behaviour probes: a standalone telnetlib3 server built through `bastproxy.libs.net.server.create_server`
  with the listener's arguments, driven by a raw `asyncio` client; a fake MUD (raw `asyncio` server) driven
  against `MudTelnetClient`; and the live proxy against Evennia on `127.0.0.1:4000`, driven over a raw
  socket.
- Q6: `uv run pytest tests/libs/net --cov=bastproxy.libs.net --cov-branch --cov-report=term-missing -q`, and
  the same command over `tests` with `-n auto`.

---

## Q1: Which telnetlib3 Private API Does the Proxy Use?

**Verified** by `grep` over `src/bastproxy/libs/net/` (every `self._`, `telnetlib3.` write, `.protocol`,
`_extra` and `telopt` use) and by reading the installed telnetlib3 5.0.1 source.

```text
$ grep -n "self\._buffer\|self\._eof\|_wait_for_data\|_wakeup_waiter\|_maybe_resume_transport" src/bastproxy/libs/net/mud.py
411:        if not self._buffer:
413:        if not self._prompt_marks or self._prompt_marks[-1] != len(self._buffer):
414:            self._prompt_marks.append(len(self._buffer))
415:        self._wakeup_waiter()
419:        return bool(self._prompt_marks) or _LINE_END.search(self._buffer) is not None
423:        raw = bytes(self._buffer[:keep])
425:        del self._buffer[:end]
427:        self._maybe_resume_transport()
434:            match = _LINE_END_FINAL.search(self._buffer, 0, mark)
438:            match = _LINE_END.search(self._buffer)
451:        if not self._buffer:
453:        match = _LINE_END_FINAL.search(self._buffer)
456:        return self._consume(len(self._buffer), len(self._buffer), ended=False)
473:            if self._eof:
475:            if not self._buffer:
476:                await self._wait_for_data("read_mud_line")
480:                    await self._wait_for_data("read_mud_line")
$ grep -rn "_extra\|\.protocol\b" src/bastproxy/libs/net/
src/bastproxy/libs/net/client.py:110:        self.telnet_server: TelnetServer | None = self.writer.protocol
src/bastproxy/libs/net/mud.py:98:        # rows = self.writer.protocol._extra['rows']        (a comment)
```

Issue #304 listed three reader names. The code uses five, and one private class attribute and one private
module dict besides.

| # | Private name | File and symbol | Used for | Public 5.x alternative | Safe across a minor release |
|---|--------------|-----------------|----------|------------------------|-----------------------------|
| 1 | `TelnetReader._buffer` (bytearray) | `src/bastproxy/libs/net/mud.py`: `MudTelnetReader.mark_prompt`, `line_ready`, `_consume`, `_take_complete`, `_take_pending`, `read_mud_line` | Search for line endings without consuming, take a prefix, record a prompt mark as a buffer offset | None. The public reads (`read`, `readline`, `readuntil`, `readuntil_pattern`, `readexactly`) consume or block; there is no peek or buffered-length call, and `readuntil_pattern` cannot return a partial line or a position | Yes for 5.0.1 to 5.0.2 (**verified** by diff: no change). Guarded by the canary test, which checks existence only |
| 2 | `TelnetReader._eof` | `MudTelnetReader.read_mud_line` | Tell "EOF received" from "no data yet" while bytes remain buffered | None. `at_eof()` is `_eof and not _buffer`, so it is false while bytes remain, which is the case this code must detect | Same as #1 |
| 3 | `TelnetReader._wait_for_data(func_name)` | `MudTelnetReader.read_mud_line` (two calls) | Wait for the next chunk, with and without a timeout | None. Every public read waits inside the base class. The proxy could keep its own `asyncio.Event`, set from an overridden `feed_data`, and drop #3 and #4 | Same as #1. It raises `RuntimeError` if another coroutine already waits, so a second reader task on the same reader would fail |
| 4 | `TelnetReader._wakeup_waiter()` | `MudTelnetReader.mark_prompt` (called from the IAC GA and EOR callback) | Wake a `read_mud_line` that waits for data, because a prompt mark is new information | None. Same own-event alternative as #3 | Same as #1 |
| 5 | `TelnetReader._maybe_resume_transport()` | `MudTelnetReader._consume` | Resume the paused transport after the buffer shrinks (flow control) | None. The public reads call it themselves; consuming from `_buffer` directly means calling it too | Same as #1 |
| 6 | `BaseClient._reader_factory_encoding` (class attribute) | `src/bastproxy/libs/net/mud.py`: `MudTelnetClient._reader_factory_encoding = MudTelnetReader` | Make the MUD connection build `MudTelnetReader` | None on the client. The server side has the public `reader_factory_encoding` argument of `TelnetServer.__init__` (`server.py:111`); `open_connection` and `TelnetClient.__init__` have no equivalent | Same as #1 (**verified**: the canary test asserts the attribute) |
| 7 | `telnetlib3.telopt._DEBUG_OPTS` (dict, written) | `src/bastproxy/libs/net/__init__.py`, module level | Name a telnet option byte in telnetlib3's log lines | None, and not needed: see Q4 | The write is a no-op in effect. It changes only log text. **Status:** fixed by #67 (patch removed) |

Not private, but not documented for subclassing either (**read**): `TelnetServer.begin_advanced_negotiation`
is documented as a callback to override (`server_base.py:273`). `TelnetClient.connection_made` documents
"ensure `super().connection_made(transport)` is called when derived". `TelnetClient.setup_gmcp` and
`setup_zmp` are public names with one-line docstrings; no page promises them as extension points.

Everything else the layer calls is public (**read**): `open_connection`, `create_server` and their keyword
arguments (`term`, `shell`, `encoding`, `client_factory`, `protocol_factory`, `compression`, `force_binary`,
`connect_maxwait`, `timeout`), `TelnetReaderUnicode`, `TelnetWriterUnicode`, `writer.write`, `drain`, `send_iac`,
`send_ga`, `set_iac_callback`, `write_eof`, `close`, `is_closing`, `connection_closed`, `get_extra_info`, `protocol`,
`reader.decode`, `exception`, `at_eof`, `feed_eof`, `readline`, and the constants `telnetlib3.telopt.GA` and `CMD_EOR`.
The mypy override `telnetlib3.*` with `ignore_missing_imports = true` is unnecessary: telnetlib3 ships
`py.typed` (**verified** by `ls`). It is harmless.

**Finding.** The private surface is bounded and tested for existence. Its risk is a change of behaviour behind
a name that still exists, which the canary cannot see. `MudTelnetReader` is covered by behavioural tests
in `tests/libs/net/test_mud_connection.py`, so a behaviour change would fail those. The sound fix is not
to remove the names (no public API exists) but to ask telnetlib3 for a public peek and buffered-length call,
or to move #3 and #4 to an own event. Neither is worth an issue today.

---

## Q2: Does the Proxy Call Deprecated API?

**Verified. Result: no.**

```text
$ BASTPROXY_HOME=$PWD/tmp/bh304 uv run pytest tests/libs/net -W error::DeprecationWarning \
    -W error::PendingDeprecationWarning -p no:cacheprovider -q
INTERNALERROR> pytest.PytestDeprecationWarning: The configuration option
  "asyncio_default_fixture_loop_scope" is unset.
```

That first run fails before any test: pytest-asyncio warns about the project's config, and the warning
becomes an error. It is unrelated to telnetlib3 (#310 sets the option). With that one warning left as a
warning:

```text
$ ... -W error::DeprecationWarning -W error::PendingDeprecationWarning \
    -W ignore::pytest.PytestDeprecationWarning -p no:cacheprovider -q
..........................................                               [100%]
42 passed in 3.91s
```

What telnetlib3 5.0.1 deprecates (**verified** by `grep -n "warnings.warn\|[Dd]eprecat"` over the package):

| Deprecated | Where in telnetlib3 | Used by bastproxy |
|------------|---------------------|-------------------|
| `TelnetReader.connection_closed` (property; warns) | `stream_reader.py:442` to `453` | No. `writer.connection_closed` is a different, current property (`stream_writer.py:437`) |
| `TelnetReader.close()` (warns) | `stream_reader.py:456` to `468` | No. The code calls `reader.feed_eof()` |
| `TelnetWriter.mssp_data`, `atcp_data`, `aardwolf_data`, `mxp_data`, `comport_data` (use `writer.ctx.*`) | `stream_writer.py:448` to `495` | No (**verified** by `grep`; the protocol handlers are not used yet) |
| the stdlib `telnetlib` module (its constants are exported from the `telnetlib3.telopt` module) | `telopt.py:1` to `6` | No. Only `telnetlib3.telopt` is imported |

Live session (**verified**): the proxy started with `PYTHONWARNINGS=error::DeprecationWarning`, connected to
Evennia on `127.0.0.1:4000` and relayed the welcome screen, `look` and a command with non-ASCII text through two
clients. Startup did not fail on a deprecation, and the log has no deprecation line:

```text
$ grep -c -i "deprecat" tmp/agents/claude/implement-issue-304/proxy.log
0
```

The Python version of this run was 3.12.12. The code calls `asyncio.get_event_loop()` in
`MudConnection.send_to` and `ClientConnection.send_to`; on 3.14 that call raises when no loop is running
(**read**). Both are called from inside the loop, so they work.

---

## Q3: What Does the Proxy Reimplement?

| Feature | Where the proxy does it | What telnetlib3 5.0.1 provides | Verdict |
|---------|-------------------------|--------------------------------|---------|
| Echo negotiation (#66) | `src/bastproxy/libs/net/telnet.py`: `echo_on`, `echo_off` return raw `IAC WILL/WONT ECHO`; `ClientConnection.setup_client` and `process_data_from_not_logged_in_client` send them with `writer.send_iac` | `writer.iac(WILL, ECHO)` records the option state; telnetlib3 also negotiates ECHO itself after TTYPE (`TelnetServer._negotiate_echo`) | **Switch** (#66). **Verified**: both a plain and a MUD client got `WILL ECHO` twice, see Q7. **Status:** fixed by #66; the helpers were removed by #67 |
| Idle and connected time (#90) | `ClientConnection.connected_time`, `connected_length` | `TelnetServer.duration` and `.idle` (`_base.py:108`, `:114`) | **Switch for idle**, keep `connected_time` for the timestamp (#90) **Status:** fixed by #90 |
| Client terminal type, size | `src/bastproxy/plugins/core/clients/plugin/_clients.py`: `_api_client_list_formatted` writes the constant `"Term Type"`; `ClientConnection.rows` is set to 24 and never read | `writer.get_extra_info("TERM")`, `"rows"`, `"cols"` | **Switch** (#307; terminal type fixed by #307, rows and columns still open). **Verified**: `TERM extra: xterm` after the client answered TTYPE. Rows and columns need NAWS, which is not negotiated (#66) |
| Terminal type and size sent to the MUD | `MudConnection.term_type = "bastproxy"`; no size | `open_connection(term=, cols=, rows=)`; `writer` answers NAWS from them | **Feature** (#308). **Verified**: the MUD connection answers `DO NAWS` with `WILL NAWS` and `SB NAWS`, from the fixed 80 by 25 default |
| Line handling | `MudTelnetReader.read_mud_line`, `_LINE_END`, `_LINE_END_FINAL` | `TelnetReaderUnicode.readline()` splits at `\r\n`, `\r\0`, a lone `\r` and `\n`, with no wait, no `\n\r` and no partial line (**read**, `stream_reader.py:470` to `545`) | **Keep.** It does what `readline()` does not: `\n\r`, a wait for a split ending, partial lines and prompt marks (#65). There is no public alternative (Q1) |
| Encoding fallback (#63) | `force_binary=True` in `Listeners._create_listeners` (both listeners) and `MudConnection.connect_to_mud` | `force_binary` is the public telnetlib3 argument | **Keep.** It is the telnetlib3 feature, not a reimplementation. The alternative, negotiating BINARY from `begin_advanced_negotiation`, is #66 |
| Decode errors | none: the server listeners keep telnetlib3's default `encoding_errors="strict"`; the MUD client uses telnetlib3's client default `"replace"` | `create_server(encoding_errors=...)` | **Change** (#305) |
| GMCP, MSDP, MSSP | none; the proxy declines them | `telnetlib3.mud` (`gmcp_encode`/`gmcp_decode`, `msdp_*`, `mssp_*`, `zmp_*`, `atcp_decode`, `aardwolf_decode`) and `writer.send_gmcp`, `send_msdp`, `send_mssp`, `set_ext_callback` | **Use them** when #59 and #60 land. Nothing to switch today |
| MXP, MSP, ATCP, Aardwolf | none; declined | handlers and `writer.ctx.*` data | #61 and later |
| MCCP2 and 3 | none; refused with `compression=False` on every call | `compression=` argument and automatic (de)compression | #58 |
| Option declaration | `telnet.GAME_CAPABILITIES` (empty), `telnet.advertise_features`, `telnet.code`, `telnet.iac*`, `telnet.handle` | `writer.iac`, `writer.always_will`/`always_do`/`passive_do`, the `telopt` constants | **Delete** (#67). **Verified**: see Q7. **Status:** fixed by #67 |
| Prompt marking | `MudTelnetClient.connection_made` registers `mark_prompt` for GA and EOR | `writer.set_iac_callback` is the public hook for it | **Keep.** It already uses the public hook |
| Relay example | the proxy's own two connection classes | `telnetlib3.relay_server.relay_shell` (**read**: a short example that relays one client to one server) | No. It has no multi-client, record or event model. Not a candidate |

---

## Q4: Every Patch, Override and setattr

Listed from a full `grep` of `src/bastproxy/libs/net/` (**verified**: no other `setattr`, `getattr`, `global` or assignment
to a telnetlib3 object exists). The reasons come from `git log -S` and `git log` on the file.

| # | Where | What it changes | Added by, and why | Still needed on 5.x | Alternative or action |
|---|-------|-----------------|-------------------|---------------------|-----------------------|
| 1 | `src/bastproxy/libs/net/__init__.py`, module level: `setattr(telnetlib3.telopt, item, value)` for nine names | Adds names to telnetlib3's `telopt` module | `61cd764` "refactor receiving data from the mud" (2024-11-02): "add mud protocols to telnetlib3.telnet.telopt module". telnetlib3 2.0.4 lacked them | **No** (**verified**, below) | Delete the patch (#67, corrected). **Status:** fixed by #67 |
| 2 | same file: `telnetlib3.telopt._DEBUG_OPTS[value] = item` | Renames option 102 in telnetlib3's log text from `AARDWOLF` to `A102` | same commit | **No** | Delete with #1 |
| 3 | `src/bastproxy/libs/net/server.py`: `CustomTelnetServer.begin_advanced_negotiation` is empty, and does not call `super()` | Skips everything telnetlib3 sends after the first `DO` or `WILL`: `WILL SGA`, `WILL BINARY`, `DO NAWS`, `DO CHARSET`, `WILL MCCP2`, `WILL MCCP3` | `4389d7b` "convert to using telnetlib3 library" (2023-02-14) sent `DO NEW_ENVIRON`, `DO NAWS` and `DO CHARSET`. `61cd764` (2024-11-02) commented them out: "don't negotiate charset for now" | **Partly.** It keeps SGA off, so GA reaches clients. It also blocks NAWS and BINARY, which #63 and #66 need | #66 (replace with an override that keeps `DO NAWS` and `WILL BINARY`, and no `WILL SGA`) |
| 4 | same file: `create_server` overwrites `kwargs["protocol_factory"]` | A caller cannot choose the protocol factory | `4389d7b` | Yes, as the way to install #3 | Keep; it is the public `protocol_factory` argument |
| 5 | `src/bastproxy/libs/net/mud.py`: `MudTelnetClient.setup_gmcp` and `setup_zmp` do nothing | Stops telnetlib3 5.x accepting GMCP and ZMP and sending `Core.Hello` and `Core.Supports.Set` | `19bf888` (#39): 5.0.1 accepts GMCP by default; keep the 2.0.4 behaviour until ADR-0001 is decided | **Yes, until #59.** **Verified**: the fake MUD got `DONT GMCP` and `WONT GMCP` | Keep. Risk: a protocol 5.x adds a third `setup_*` method would be accepted silently. 5.0.1 has exactly two |
| 6 | same: `MudTelnetClient._reader_factory_encoding = MudTelnetReader` | The MUD connection builds `MudTelnetReader` | `bdcd589` (#65) replaced `61cd764`'s `TelnetReaderUnicode.readline` monkey patch for `\n\r` (Aardwolf) | Yes (Q3: line handling) | Keep; see Q1 #6 |
| 7 | same: `MudTelnetClient.connection_made` calls `super()`, then `writer.set_iac_callback(GA/CMD_EOR, reader.mark_prompt)` | Marks prompts | `bdcd589` (#65) | Yes | Keep. It uses the public hook |
| 8 | same: `MudTelnetReader` private reads | Line splitting (Q1) | `bdcd589` (#65); the earlier `61cd764` patch also used `_buffer` | Yes | Keep, see Q1 |
| 9 | `src/bastproxy/libs/net/mud.py`, `src/bastproxy/libs/net/listeners.py`: `compression=False` | Refuses MCCP on every link | `19bf888` (#39) | Yes, until #58 | Keep |
| 10 | same files: `force_binary=True` | Forces UTF-8 on all links | `25d5d60` (#63, PR #70) | Yes, or negotiate BINARY (#66) | Keep |
| 11 | `MudTelnetReader.line_timeout` assigned in `mud_telnet_handler` | Own attribute, not a patch | `bdcd589` | Yes | Keep |

Evidence for #1 and #2 (**verified**, telnetlib3 5.0.1 before and after importing `bastproxy.libs.net`):

```text
$ python -c "import telnetlib3.telopt as t; ..."          # before the bastproxy import
{'MSSP': b'F', 'MSDP': b'E', 'MCCP_COMPRESS': b'U', 'MCCP2_COMPRESS': b'V', 'MXP': b'[',
 'MSP': b'Z', 'A102': None, 'ATCP': b'\xc8', 'GMCP': b'\xc9', 'AARDWOLF': b'f'}
before patch _DEBUG_OPTS[102]= AARDWOLF
$ python -c "import telnetlib3.telopt as t; import bastproxy.libs.net; ..."
after patch A102= b'f' _DEBUG_OPTS[102]= A102 name_command: A102
option_from_name AARDWOLF -> b'f'
```

All nine names exist in 5.0.1. `A102` is the same byte as `AARDWOLF` (102). After the patch the second
step also changed the log name: the fake-MUD probe shows `DONT A102` where an unpatched telnetlib3 would
print `DONT AARDWOLF`. Nothing in `src/` or `tests/` reads `telnetlib3.telopt.A102` (**verified** by `grep`).
The patch also leaves telnetlib3's `_NAME_TO_OPT` map out of date, so `option_from_name("A102")` would raise
`KeyError`. The patch runs for any import of `bastproxy.libs.net`, because the package `__init__` runs first.
**Status:** fixed by #67. `src/bastproxy/libs/net/__init__.py` no longer touches `telnetlib3.telopt`.

Evidence for #3: the bytes a client receives from `CustomTelnetServer` (**verified**, `create_server` with the
listener's arguments, a client that answers TTYPE `xterm`):

```text
b'xterm' -> ['DO TTYPE', "SB TTYPE b'\\x01'", 'WILL ECHO', 'DO NEW_ENVIRON', "SB TTYPE b'\\x01'", 'WILL ECHO', 'WONT ECHO']
WILL ECHO count: 2  WONT ECHO count: 1  DO NAWS: 0
```

No `WILL SGA`, no `WILL BINARY` and no `DO NAWS`. `DO NEW_ENVIRON` is still sent: telnetlib3 sends it from its
own deferred `_negotiate_environ`, not from `begin_advanced_negotiation`, so the empty override does not
disable "everything" as #66 says.

---

## Q5: What Changed in 5.0.2?

**Verified** by diffing the unpacked 5.0.1 and 5.0.2 wheels (excluding `tests/`):

```text
$ diff -rq x501 x502 | grep -v "/tests/\|dist-info"
Files x501/telnetlib3/accessories.py and x502/telnetlib3/accessories.py differ
Files x501/telnetlib3/guard_shells.py and x502/telnetlib3/guard_shells.py differ
Files x501/telnetlib3/server_shell.py and x502/telnetlib3/server_shell.py differ
Files x501/telnetlib3/stream_reader.py and x502/telnetlib3/stream_reader.py differ
```

- `accessories.py`: the version string.
- `guard_shells.py`, `server_shell.py`: a `UnicodeDecodeError` from `reader.read(1)` ends input, as EOF does.
  bastproxy uses neither module.
- `stream_reader.py`, `TelnetReaderUnicode`: `decode(b"", final=True)` finalizes bytes held by the incremental
  decoder at end of stream and applies `encoding_errors`; `read(n)` no longer returns more than `n`
  characters and waits for the rest of a partial character; `at_eof()` also checks a new `_pending`
  attribute; `readline()` finalizes the decoder when its bytes are the last of the stream.

Effect on bastproxy (output trimmed), from running the two reader classes on 5.0.1 and 5.0.2 over a stream that ends in half a
UTF-8 character (`ab\xc3`, then EOF):

```text
--- installed 5.0.1                         errors=strict                        errors=replace
TelnetReaderUnicode  partial char at EOF:   ['ab', '']                           ['ab', '']
MudTelnetReader      partial char at EOF:   [MudLine('ab', False, False), ...]   [MudLine('ab', ...), ...]
--- 5.0.2
TelnetReaderUnicode  partial char at EOF:   ['RAISED UnicodeDecodeError']       ['ab�', '']
MudTelnetReader      partial char at EOF:   [MudLine('ab', False, False), ...]   [MudLine('ab', ...), ...]
```

- `MudTelnetReader` is unchanged on 5.0.2: it decodes with `decode(raw)` (not final) and so drops a trailing
  half character on both versions. That is harmless; `decode(raw, final=True)` would apply the error policy.
- The client-side reader (`TelnetReaderUnicode`, strict) now raises `UnicodeDecodeError` from `readline()`
  when a client disconnects mid-character. `ClientConnection.client_read` catches only `ConnectionError`
  (**read**), so the read task ends with an exception that `libs/asynch` logs as an ERROR. The
  invalid-UTF-8 defect (#305) is the same failure on both versions; fix it before the floor moves.
  **Status:** fixed by #305.
- All 42 tests in `tests/libs/net` pass on 5.0.2 (**verified**, with the unpacked 5.0.2 package first on
  `PYTHONPATH`).

**Floor.** The floor `telnetlib3>=5.0.1` can stay: nothing in 5.0.2 is needed for a defect the proxy has
today. Raise it to 5.0.2 after #305 so the lock follows the current release and the proxy gets the
end-of-stream decoding fix (#311). `uv.lock` pins 5.0.1 and PyPI serves 5.0.2 (**verified**:
`pip download telnetlib3==5.0.2` succeeded).

---

## Q6: What Is Untested?

**Verified.**

```text
$ BASTPROXY_HOME=$PWD/tmp/bh304 uv run pytest tests/libs/net --cov=bastproxy.libs.net --cov-branch \
    --cov-report=term-missing -q
Name                                  Stmts   Miss Branch BrPart   Cover   Missing
src/bastproxy/libs/net/__init__.py        9      0      4      0 100.00%
src/bastproxy/libs/net/client.py        174    106     46      8  37.27%   96-112, 125, 146-163, 180-210, 230-279, 298-302, 342-343, 346, 358-359, 393, 398-405, 409-412, 445-451, 471-477, 499-541
src/bastproxy/libs/net/listeners.py      81     57     22      3  26.21%   74-83, 103-175, 194-202, 237-239, 242->263, 263->exit, 301-303
src/bastproxy/libs/net/mud.py           187     50     56      5  69.14%   144, 163-174, 190-202, 247-252, 271-296, 336->339, 341-351, 413->415, 470
src/bastproxy/libs/net/server.py         13      6      0      0  53.85%   39-42, 91-92
src/bastproxy/libs/net/telnet.py         75     43     24      0  32.32%   116-128, 149-161, 182-191, 211-215, 235, 255, 305-312
TOTAL                                   539    262    152     16  47.61%
42 passed
```

`uv run pytest tests -n auto --cov=bastproxy.libs.net ...` (the whole suite) reports the same
47.61%: no test outside `tests/libs/net/` reaches the package (4,854 passed, 13 skipped; the 9 integration
tests are skipped). `uv run doit coverage` was not run; the whole-suite run answers the question it would.

What the missing lines are (**read**, mapped from the line ranges to symbols):

| File | Untested | Why it matters |
|------|----------|----------------|
| `server.py` | `create_server` and so `CustomTelnetServer` (lines 91 to 92) | No test fixes the bytes a client receives at connect. #66 asks for exactly that |
| `listeners.py` | `Listeners.__init__`, `check_listeners_available` (retry, reset to defaults, exit), `reset_listener_settings`, the no-listener default, `create_listeners` | The start-up failure path is the one an operator meets with a busy port |
| `client.py` | `ClientConnection.__init__`, `send_to`, `setup_client`, `process_data_from_not_logged_in_client`, the view-only path, the telnet-command branch of `client_write`, `register_client` success, `unregister_client`, `client_telnet_handler` | The login and password path, the client's life cycle and the cleanup are untested |
| `mud.py` | `disconnect_from_mud`, `send_to`, `setup_mud`, `mud_write` (all of it), the tail of `mud_telnet_handler`, the `raise exc` branch of `read_mud_line` | The whole write side of the MUD link; and the connect-failure path (#306) |
| `telnet.py` | `iac`, `iac_sb`, `split_opcode_from_input`, `advertise_features` loop, `echo_on`, `echo_off`, `handle` | Most of these are dead or broken (#67); `echo_on` and `echo_off` carry the password masking. **Status:** fixed by #67 (dead helpers deleted, including `echo_on` and `echo_off` and their tests; only `go_ahead` remains, covered by `tests/libs/net/test_telnet.py`) |
| `__init__.py` | covered (100%) | covered by importing; no test checks what the patch does. **Status:** fixed by #67 (patch deleted; `tests/libs/net/test_telnet.py` checks that importing the package leaves `telnetlib3.telopt` alone) |

`tests/libs/net/` does hold real end-to-end tests, which carry more weight than the percentage: a real
telnetlib3 client against a raw server for GA, EOR, MCCP and GMCP refusal, line splitting at every byte
boundary (`test_split_matches_unsplit_at_every_index`), `force_binary` UTF-8 in both directions, and the
canary. The gap is the server side and the listeners.

---

## Q7: Do the Existing Issues Still Hold?

Each claim was re-measured, not repeated.

| Issue | Verdict | Evidence |
|-------|---------|----------|
| #66 echo and empty `begin_advanced_negotiation` | **Holds, two corrections** | Verified, Q4 #3: `WILL ECHO` twice for `xterm` and for `Mudlet`, no `DO NAWS`, no `WILL BINARY`, no `WILL SGA`. Correction 1: `DO NEW_ENVIRON` is still sent, so "disables everything" is too strong. Correction 2: because `WILL SGA` is not sent, SGA is the choice #66 already makes ("leave `WILL SGA` off") and it is the current behaviour, not only a plan |
| #67 telopt patch and dead helpers | **Holds, one correction** | Verified: `iac([24])` gives `b'\xff24'`; `iac_sb([24, 1])` gives `b'\xff\xfa241\xff\xf0'`; three capabilities advertise 21 bytes, not 9; `split_opcode_from_input(b"Fine*")` gives `(b'F*', 'ine')`. Only `advertise_features`, `echo_on`, `echo_off` and `go_ahead` are called (**verified** by `grep`). Correction: the patch does not "still add `A102`". `A102` is `AARDWOLF`, defined in 5.0.1; the whole patch can go, not all but one name (Q4). **Status:** fixed by #67 |
| #90 idle time | **Holds, one claim is stale** | `idle` and `duration` exist on `_base.py:108` to `:117` and use naive `datetime.now()`. The claim that `idle` "would raise before any data is received" is wrong: `_last_received` is set in `connection_made`. **Verified**: `idle at connect, no data received: 0.201`. Also, `self.telnet_server` is never `None` after `__init__` (it is `writer.protocol`), and it is read nowhere today (**verified** by `grep`). `idle` counts every received byte, negotiation included, not only typed input **Status:** fixed by #90; `ClientConnection.idle` feeds the Clients table's Idle column |
| #272 GA to clients that agreed SGA | **Does not hold as written** | "The proxy's telnetlib3 server sends `WILL SGA` unless `line_mode` is set" is true of the stock `TelnetServer`, but `CustomTelnetServer.begin_advanced_negotiation` replaces that code. **Verified**: no `WILL SGA` in the bytes above, so `local_option.enabled(SGA)` is false and `send_ga()` sends GA (read, `stream_writer.py:1108`). The problem returns when #66 restores the stock override. Write the issue as a dependency of #66 |
| #271 accept SGA from the MUD | **Holds** | **Verified**: the fake MUD's `WILL SGA` is answered `DO SGA` |
| #83 negotiation records | **Holds** | **Verified** on the live session: `#bp.core.proxy.info` shows `Options         :` empty for the MUD; `MudConnection.__init__` has the option listing commented out. The MUD link also accepts `SGA`, `ECHO`, `EOR`, `BINARY`, `CHARSET` and `STATUS` (**verified**) with no record |
| #58 to #61 protocols | **Hold** | **Verified**: the fake MUD got `DONT GMCP`, `DONT MSDP`, `DONT MSSP`, `DONT MCCP2_COMPRESS`, `DONT MXP`, `DONT MSP`, `DONT ATCP` and `DONT ZMP` |
| #63 (closed) | Holds | `force_binary=True` is on all three calls (**read**); `tests/libs/net/test_force_binary.py` covers it |
| #39 (closed), item "evaluate whether the readline patch can drop private internals" | **Answered**: it cannot (Q1) | |

The corrections are written out in the proposed edits to #66, #67, #90 and #272.

---

## Q8: Patterns and Anti-Patterns

| # | Pattern | File and symbol | Verdict |
|---|---------|-----------------|---------|
| 1 | Subclass telnetlib3 types and install them through public arguments (`client_factory`, `protocol_factory`) | `MudTelnetClient`, `CustomTelnetServer` | **Keep.** It is the supported seam |
| 2 | Import-time side effect: `src/bastproxy/libs/net/__init__.py` mutates `telnetlib3.telopt` and a private dict when anything in `bastproxy.libs.net` is imported | `src/bastproxy/libs/net/__init__.py` | **Change.** Global state, and unneeded (Q4). Delete it (#67). **Status:** fixed by #67 |
| 3 | Import-time `try/except ImportError` that prints and calls `sys.exit(1)` | `src/bastproxy/libs/net/server.py`, top | **Change** (#309). telnetlib3 is a hard dependency in `pyproject.toml`, so the branch is dead; a `print` and `sys.exit` in an import is the "silent failure" pitfall in reverse. Coverage shows lines 39 to 42 unreached |
| 4 | Empty override with a `Raises: NotImplementedError` docstring that does not raise | `CustomTelnetServer.begin_advanced_negotiation` | **Change** (#66; docstring in #309) |
| 5 | Catch-all `contextlib.suppress(Exception)` around `ipv4_task.result` and `ipv6_task.result` | `Listeners.check_listeners_available`, two blocks | **Change, low priority** (#309). It hides why a listener failed to bind: the error is replaced by the generic "did not start ... please check errors" line. Log the exception |
| 6 | `contextlib.suppress(AttributeError)` around `drain()` | `register_client` (banned client) | **Keep, narrow.** It guards a closed transport. It could name the case in a comment |
| 7 | One narrow `except ConnectionError` | `ClientConnection.client_read` | **Change** (#305): it misses `UnicodeDecodeError`, which kills the client |
| 8 | Connection state defaulting to the connected state | `MudConnection.connected = True` in `__init__` | **Change** (#306, fixed). Verified defect |
| 9 | Hard-coded placeholder as data | `_api_client_list_formatted`: `"term_type": "Term Type"` | **Change** (#307). Verified defect; **fixed by #307** |
| 10 | Unused state: `ClientConnection.rows` (set to 24, never read), `telnet_server` (read nowhere until #90), `MudConnection.term_type` comment lines about `_extra`, `telnet.main_negotiations`, `telnet.opcode_match` | `client.py`, `mud.py`, `telnet.py` | **Change** (#67; rest in #309). **Status:** the `telnet.main_negotiations` and `telnet.opcode_match` part is fixed by #67 |
| 11 | Copy-pasted log label: `mud_write` logs telnet commands to the MUD as `"to_client"` | `MudConnection.mud_write` | **Change** (#309) |
| 12 | Copy-pasted headers: `mud.py` says `Filename: libs/net/client.py` and `File Description: Client connection handling.` | `src/bastproxy/libs/net/mud.py`, lines 1 to 6 | **Change** (#309) |
| 13 | A hidden global: `telnet.GAME_CAPABILITIES` list, mutated by nothing, read by `advertise_features` | `src/bastproxy/libs/net/telnet.py` | **Change** (#67). **Status:** fixed by #67 |
| 14 | `bastproxy.libs.net.*` is in the mypy `ignore_errors = true` list | `pyproject.toml` | **Keep for now.** This is the legacy strictness tracked in #6; do not widen it. Type-checking `libs/net` is a candidate for #6 |
| 15 | A listener bound to `"localhost"` is described as IPv4 but binds IPv6 too | `Listeners._create_listeners`, `ipv4address` default | **Observation**, see Other Observations |
| 16 | `asyncio.sleep(1)` at the end of both handlers | `client_telnet_handler`, `mud_telnet_handler` | **Keep.** Gives the writer time to flush; comment it if touched |
| 17 | Paths, `subprocess`, YAML: not used in `libs/net` | n/a | Nothing to review |
| 18 | Dependency injection: `API(owner_id=...)` constructed in `__init__`; the telnetlib3 types are class attributes and arguments, so tests can replace them | `Listeners`, `MudConnection`, `ClientConnection` | **Keep** |

---

## New Defects and Changes

Each is filed as its own issue. The text of each is in the issue; the table is the index.

| Issue | Type | Title | Found by | Page reference |
|-------------|------|-------|----------|----------------|
| #305 | bug | A client that sends invalid UTF-8 is disconnected, and a client that drops mid-character logs an error on telnetlib3 5.0.2 | Verified live and by probe | Q3, Q5, Q8 #7 |
| #306 | bug | A failed connection to the MUD leaves the proxy marked as connected | Verified live | Q8 #8 |
| #307 | bug | The Clients table shows the literal text "Term Type" instead of the client's terminal type | Verified live | Q3, Q8 #9 |
| #308 | feature | Forward the client's terminal type and window size to the MUD | Verified (MUD link answers NAWS with 80 by 25) | Q3 |
| #309 | chore | Clean up stale headers, a wrong log label, the dead import guard and swallowed listener errors in `libs/net` | Read | Q8 #3, #4, #5, #10, #11, #12 |
| #310 | chore | Add tests for the untested paths of `libs/net` and set the pytest-asyncio loop scope | Verified coverage | Q2, Q6 |
| #311 | chore | Raise the telnetlib3 floor to 5.0.2 | Verified diff | Q5 |

Existing issues to update instead of duplicating: #66, #67, #90 and #272 (Q7). #271, #83 and #58 to #61
hold as written.

Order: #305 before #311. #308 depends on #66. #310 should follow #66, #67 and #306, so
the tests do not pin code those changes remove.

The `telnetlib3` side effect of #305, in numbers (**verified**, live): after one `ab\xc3(` line a logged-in
client is closed, and the log has

```text
ERROR - asyncio - exception in task f2136c07... telnet read 'utf-8' codec can't decode byte 0xc3 in position 2: invalid continuation byte
UnicodeDecodeError: 'utf-8' codec can't decode byte 0xc3 in position 2: invalid continuation byte
```

and the next `look` on the same socket gets zero bytes (`closed = True`).

Evidence for #306 (**verified**, live, a fresh `BASTPROXY_HOME` where `mudhost` and `mudport` are unset):

```text
>>> #bp.core.proxy.connect
#BP: Connecting to the mud
ERROR - asyncio - exception in task Mud Connect Task Multiple exceptions: [Errno 111] Connect call failed ('::1', 0, 0, 0), [Errno 111] Connect call failed ('127.0.0.1', 0)
>>> #bp.core.proxy.set mudhost 127.0.0.1 / mudport 4000
>>> #bp.core.proxy.connect
#BP: The proxy is currently connected to the mud
```

No MUD connection exists at that point (`ss` and the log show none). `#bp.core.proxy.disconnect` and a second
`connect` then work.

---

## Other Observations

- **Environment sent to the MUD.** The MUD link answers `NEW_ENVIRON` with the keys in
  `TelnetClient.DEFAULT_SEND_ENVIRON` (`TERM`, `LANG`, `COLUMNS`, `LINES`, `COLORTERM`); `USER`, `HOME` and
  `SHELL` are only sent when asked for by `send_environ=`, which the proxy never passes (**read**,
  `client.py:55`, `:280` to `:306`). The MUD can request a charset change; the proxy refuses a charset it
  does not hold (**verified**: `SB CHARSET REQUEST ;ISO-8859-1` was answered `REJECTED`, and the next UTF-8
  line decoded correctly).
- **IPv4 listener on `localhost`.** With `ipv4address` at its default `localhost`, `ss` shows listeners on both
  `127.0.0.1:9999` and `[::1]:9999`, while the start-up log says "Listening on IPv4 port 9999" and the IPv6
  setting is False (**verified**). Clients arrive as `::1`. telnetlib3 passes the host name to `asyncio`, which
  binds every address it resolves. Not a defect by itself; a note for anyone who sets up IP bans, which key on
  the address string.
- **`timeout=3600` on the listeners** is telnetlib3's idle timeout for a client. A client silent for an hour is
  dropped. Intended or not, it is not documented in [Data Flow](data_flow.md) (**read**).
- **`MudTelnetClient` accepts `CHARSET`, `SGA`, `EOR`, `ECHO`, `BINARY` and `STATUS` from the MUD** (**verified**).
  The 2024 commit said "don't negotiate charset for now". The reply to a charset request is safe (above), but
  the policy is implicit; #271 and #83 are the places to make it explicit.
- **Docs.** [Data Flow](data_flow.md) was checked against the code for the connection classes: every claim on
  `ClientConnection`, `MudConnection`, `MudTelnetReader` and `MudTelnetClient` matched. It was not changed.
  [README](README.md) has no network page. It does not say that `MudTelnetClient` declines GMCP and ZMP; that is
  stated in the class docstring and in #39.
