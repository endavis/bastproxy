---
title: Debugging
description: Tracing bastproxy's event and plugin flow with hunter, without adding log lines
audience:
  - contributors
  - ai-agents
tags:
  - debugging
  - tooling
---

# Debugging

## Tracing event flow with hunter

[hunter](https://pypi.org/project/hunter/) traces function calls with a query, so you can see what raised what, in what order and with which arguments, without editing code or adding log lines. It is not a project dependency: run it on demand with `uv run --with hunter`, which leaves `pyproject.toml` and `uv.lock` untouched. The evaluation behind this page is on [#429](https://github.com/endavis/bastproxy/issues/429).

### Trace a startup

This script starts bastproxy up to the proxy-ready event with the listeners and the async loop stubbed out, and prints every call of the events plugin's raise function:

```python
import hunter
from hunter import CallPrinter, Q

out = open("tmp/hunter-trace.txt", "w")
hunter.trace(
    Q(module_contains="plugins.core.events", function="_api_event_raise", kind="call"),
    action=CallPrinter(stream=out, filename_alignment=0, repr_limit=120, force_colors=False),
)

import bastproxy as bp
import bastproxy.libs.net.listeners as listeners
from bastproxy import MudProxy

bp.run_asynch = lambda: None
listeners.Listeners.create_listeners = lambda self: None
MudProxy().run({"port": -1, "IPv4_address": "", "quiet": True})
hunter.stop()
out.close()
```

Save it outside `src/` (for example under `tmp/`) and run it with a throwaway home directory:

```bash
mkdir -p tmp/hunter-home
BASTPROXY_HOME=$PWD/tmp/hunter-home uv run --with hunter python tmp/hunter_startup.py
```

The indentation in `tmp/hunter-trace.txt` is call depth, so a raise made while handling another raise appears nested under it.

### Trace one event

Tracing every raise nests the whole startup and gets hard to read. Filtering on the event name is usually more useful. Replace the `hunter.trace(...)` call with a predicate on the call's locals:

```python
hunter.trace(
    Q(
        lambda ev: ev.kind == "call"
        and ev.function == "_api_event_raise"
        and ev.locals.get("event_name") == "ev_bastproxy_proxy_ready"
    ),
    action=CallPrinter(stream=out, filename_alignment=0, repr_limit=120, force_colors=False),
)
```

### Keeping the output readable

- `filename_alignment=0` stops hunter padding long absolute paths into a column.
- `repr_limit` truncates the reprs of plugin objects and large arguments.
- Write to a file (`stream=`) rather than the terminal; a full startup produces over a hundred raise calls.

### Cost

Tracing slows the traced code down several times over (the startup above went from about 0.3 s to about 2.5 s). Use it in an offline session, never on a live proxy.
