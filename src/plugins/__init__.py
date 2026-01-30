"""Namespace shim exposing ``bastproxy.plugins`` as top-level ``plugins``.

The plugin loader discovers modules under the ``plugins`` prefix. This package
extends the search path so imports like ``plugins.core...`` resolve to
``bastproxy.plugins`` without rewriting existing plugin identifiers.
"""

from __future__ import annotations

import pkgutil
from pathlib import Path

# Allow "plugins" to point at the actual bastproxy.plugins package directory.
__path__ = [
    *pkgutil.extend_path(__path__, __name__),
    str(Path(__file__).resolve().parent.parent / "bastproxy" / "plugins"),
]
