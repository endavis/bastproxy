---
title: "ADR-0012: Plugins own telnet options the core does not handle through a generic hook"
description: A plugin registers a telnet option number and owns its negotiation, events and subnegotiations through a hook on the recording telnet writer, while the core interprets no payload.
date: 2026-11-18
audience:
  - contributors
tags:
  - adr
---

# ADR-0012: Plugins own telnet options the core does not handle through a generic hook

## Status

Accepted

## Context

[ADR-0001](0001-terminate-mud-telnet-protocols-at-the-proxy.md) terminates the telnet protocols the proxy implements. Issue #566 needs a way to use a protocol the core does not know, such as Aardwolf's option 102, without putting game logic in the core. The wire protocol belongs to the core, since only it sees the negotiation; what the bytes mean belongs to a plugin.

telnetlib3 5.0.3 does not leave unknown options alone: it names 102 (`AARDWOLF`) and answers `DONT` to a `WILL` for it, sends `WILL` to an unsolicited client `DO`, decodes an `SB 102` itself, and raises `ValueError("SB unhandled")` for an `SB` of a fully unknown option.

## Decision

1. **Intercept in the writer.** `RecordingTelnetWriter` overrides `handle_do`, `handle_dont`, `handle_will`, `handle_wont` and `handle_subnegotiation`. For an option a plugin claimed it answers and dispatches itself and never calls telnetlib3; every other option takes the path it took before, except a subnegotiation for an option that is neither built in nor owned by a plugin, which is dropped with a debug log and never reaches telnetlib3. `telnetlib3`'s `always_do` and `passive_do` are not used: `always_do` sends a proactive `DO` on connect that the MUD never asked for, and `passive_do` covers only telnetlib3's own MUD-protocol list and leaves the `SB` handling untouched.
2. **Registration.** `libs.net.protocols:telopt.register` claims an option number (0-254) for an owner, with `mud`, `client` and `forward` flags. One owner per option. Options telnetlib3 or the proxy handle themselves (BINARY, ECHO, SGA, STATUS, TM, LOGOUT, SNDLOC, TTYPE, EOR, NAWS, TSPEED, LFLOW, LINEMODE, XDISPLOC, NEW_ENVIRON, CHARSET, COM_PORT, MCCP2, MCCP3, GMCP, MSDP, MSSP, MXP, ZMP, EXOPL) cannot be claimed.
3. **MUD link.** A `WILL` for a claimed option is answered `DO`. An option the MUD offered before the plugin registered was refused, so registering sends `DO` then (RFC 1143 allows asking again). An option still enabled on the MUD link when it is registered raises `_enabled` at once, without a new `DO`, so a plugin reload keeps working. An `SB` for an option outside the built-in list that no plugin owns is dropped with a debug log and never reaches telnetlib3.
4. **Client links.** The proxy offers `WILL` to a client when it logs in and, on register, to clients that are logged in. A client's `DO` is accepted only for a claimed option and only after login; otherwise it is answered `WONT`. A client's `WILL` for such an option is answered `DONT` (#705). And an option outside the built-in list is never negotiated with a client that has not logged in (#703). A client's subnegotiation for such an option before login is discarded. The MUD's subnegotiations are forwarded to logged-in clients that agreed, on by default and switchable with `telopt.forward.set`. A client's subnegotiation is raised as an event from a logged-in client and never forwarded to the MUD.
5. **Events** are named by option number (`ev_libs.net.mud_telopt_<n>`, `_enabled`, `_disabled` and `ev_libs.net.client_telopt_<n>`) and are added when the option is registered, so they are not in `PROTOCOL_EVENTS`. `data` is raw `bytes` with IAC unescaped. The MUD link raises `_disabled` on disconnect.
6. **Cleanup.** A plugin's options are unregistered when it unloads: unregistering raises `_disabled` and sends `WONT` to clients that enabled the option, and sends no `DONT` to the MUD. Turning a MUD feature off is the owning plugin's job.
7. **Game logic stays in plugins.** The core frames, escapes and records payloads and interprets none of them.

## Rationale

- **Writer override:** it is the one place that sees every negotiation before telnetlib3 answers it, and it is how GMCP, MSDP and MXP are already handled.
- **Re-asking with `DO`:** telnetlib3 refused the early `WILL` without remembering it, so the writer keeps every option the peer offered.
- **No `DONT` on unregister:** a MUD may answer neither `DONT` nor `DO` (Aardwolf, option 102), so a reload that sent `DONT` could never turn the option back on. Rejected alternatives: a per-registration `DONT` opt-in, and a grace timer before sending `DONT`.
- **Option-number event names:** the events depend on the number, so a static tuple cannot hold them.

## Consequences

- A plugin gets a new telnet protocol with no core change.
- Clients get no cache replay for a claimed option; the owner sends what a late joiner needs.
- The built-in list must grow when the core starts to handle another option.

## Related Documentation

- [Data Flow: Custom telnet options](../claude/data_flow.md#custom-telnet-options-566-adr-0012)
- [Plugin Developer Guide: Owning a telnet option](../plugin-developer-guide.md#owning-a-telnet-option)
- [Event System](../claude/event_system.md)
- Issues #566, #586 and #703; related [ADR-0001](0001-terminate-mud-telnet-protocols-at-the-proxy.md).
