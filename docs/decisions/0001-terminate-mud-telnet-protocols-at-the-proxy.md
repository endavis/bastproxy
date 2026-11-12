---
title: "ADR-0001: Terminate MUD telnet protocols at the proxy"
description: bastproxy terminates GMCP, MSDP, MSSP, MCCP and MXP on each link and re-sends them per client, instead of passing protocol bytes through.
date: 2026-11-02
audience:
  - contributors
tags:
  - adr
  - networking
---

# ADR-0001: Terminate MUD telnet protocols at the proxy

## Status

Accepted

## Context

bastproxy sits between one MUD connection and any number of client connections. MUD servers offer out-of-band and transport protocols on top of telnet: GMCP (201), MSDP (69), MSSP (70), MCCP2/3 (86/87) and MXP (91). Today bastproxy handles none of them. `GAME_CAPABILITIES` in `src/bastproxy/libs/net/telnet.py` is empty, and telnetlib3 2.0.4 refuses every offer (`Unhandled: WILL GMCP` and so on, observed against Evennia 6.1.0).

telnetlib3 5.0.1 (#39) provides decode/encode functions and `handle_*` callbacks for GMCP, MSDP and MSSP, MCCP2/3 compression, and MXP subnegotiation capture. By default it accepts GMCP and MCCP passively on the client side, and on GMCP it sends its own `Core.Hello` and a fixed `Core.Supports.Set`.

Telnet option negotiation is per link. The MUD link has one negotiation state; each client link has its own. Clients connect and disconnect independently, and they differ in what they support.

### Options considered

1. **Pass through.** Forward IAC negotiation and subnegotiation bytes between the MUD and the clients unchanged.
   - MCCP cannot pass through: the proxy has to decompress the stream to run triggers and line handling, so it terminates MCCP on the MUD link anyway.
   - The MUD link has one negotiation state, but with several clients each client answers the same `WILL GMCP` differently. There is no single answer to forward.
   - A client that connects after negotiation has finished never sees the offer, and has none of the state (character vitals, room) that was sent before it joined.
   - Plugins would have to parse raw IAC bytes to read protocol data.
2. **Terminate.** bastproxy is the protocol endpoint on each link. On the MUD link it negotiates as a client, decodes each protocol with telnetlib3 and publishes the data as events. On each client link it negotiates as a server, and re-encodes data for the clients that accepted that protocol.
3. **Hybrid.** Terminate the transport protocols (MCCP, and MSSP, which is metadata) and pass GMCP, MSDP and MXP payloads through as opaque bytes to clients that negotiated them.
   - This avoids re-encoding, but it inherits pass-through's problems for the protocols that carry state (late joiners, Core.Supports conflicts), and plugins still cannot read or change GMCP and MSDP.

## Decision

Terminate MUD telnet protocols at the proxy (option 2).

- **MUD link:** bastproxy accepts the protocols it implements, decodes them with telnetlib3 5.x handlers and raises one event per message (for example `ev_libs.net.mud_gmcp` with the package name and decoded data). It accepts MCCP2/3 and decompresses before line processing.
- **Client links:** bastproxy offers each protocol it implements to every client. Each client's negotiation state is kept on its client record, and data is re-encoded only for clients that accepted the protocol.
- **GMCP `Core.Supports`:** the set sent to the MUD is the union of the modules plugins ask for and the modules connected clients ask for. It is re-sent when that union changes. telnetlib3's automatic handshake is disabled, so the proxy owns `Core.Hello` and `Core.Supports`.
- **Late joiners:** the proxy caches the latest value of each GMCP package and MSDP variable, and replays it to a client when that client enables the protocol.
- **MCCP:** each link negotiates compression on its own. Compression to the MUD does not depend on compression to any client.
- **MSSP:** the proxy keeps the MUD's MSSP data. It answers clients' MSSP requests itself.
- **MXP:** the proxy passes MXP tags to clients that negotiated MXP, and strips them for clients that did not. MXP is the lowest priority.
- **NAWS:** the MUD link reports one window size: by default the size of the most recently active full-login client that reported one, overridable with the `mudwindowsize` setting (`client`, `off` or `COLSxROWS`). The terminal type is not forwarded and stays `bastproxy` ([data flow](../claude/data_flow.md)).
- **SGA and prompt marking:** the proxy refuses SGA from the MUD (`WILL SGA` gets `DONT SGA`), so the MUD keeps sending `IAC GA` after prompts and the proxy marks them ([data flow](../claude/data_flow.md)). Whether a client agreed SGA is decided on the client link on its own (#272).

## Rationale

- With several clients, terminating is the only model where negotiation stays correct: a client's choice affects its own link only, never the MUD link or other clients.
- MCCP has to be terminated anyway, so pass-through saves no complexity.
- Events make protocol data available to plugins, which matches the existing event system. For example, a plugin can read vitals from GMCP instead of parsing prompt lines with triggers.
- The cache gives late joiners and reconnecting clients the current state, which suits a proxy whose clients come and go.
- telnetlib3 5.x already provides the decoders and callbacks, so terminating does not mean implementing the protocols from scratch.

The cost is re-encoding on the client side and a cache to maintain. Each protocol also needs its own tests on both links.

### SGA and prompt marking

Measured against Evennia 6.1.0 (raw socket, login, four `look` commands, bytes after the prompt):

| Reply to `WILL SGA` | `IAC GA` after prompt | `IAC EOR` | Output ends |
| --- | --- | --- | --- |
| `DO SGA` | 0 | 0 | `Exits: tutorial\r\n` (no GA) |
| `DONT SGA` | 1 | 0 | `...\r\n\xff\xf9` |

Evennia offered WILL for SGA, MCCP2, MSSP, MSDP, GMCP and MXP and never WILL EOR, so relying on EOR would give no prompt marks there. Accepting SGA turns GA off, so the proxy refuses it. This fits "each link negotiates on its own": it concerns the MUD link only.

## Related Issues

- Issue #40: Decide how bastproxy handles MUD telnet protocols
- Issue #39: Upgrade telnetlib3 from 2.0.4 to 5.0.1 (prerequisite)
- Issue #58: Support MCCP2/3 compression on the MUD and client links
- Issue #59: Terminate GMCP and MSDP and publish them as events (MUD side first)
- Issue #60: Cache MUD MSSP data and answer client MSSP requests
- Issue #61: Pass MXP to clients that negotiate it and strip it for others
- Issue #333: Replay MXP element and entity definitions to late-joining clients
- Issue #271: Decide whether the proxy accepts SGA from the MUD
- Issue #272: Send a prompt signal (EOR, else GA) to clients
- Issue #329: Offer MCCP3 on client links
- Issue #308: Forward the client's window size to the MUD

## Related Documentation

- [Data flow](../claude/data_flow.md): how MUD and client data move through `src/bastproxy/libs/net/` today
- [Event system](../claude/event_system.md): how protocol events will reach plugins
