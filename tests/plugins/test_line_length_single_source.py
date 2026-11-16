"""The ``linelen`` setting is read in one place, ``line.length.get`` (#421).

Everything else asks ``plugins.core.proxy:line.length.get`` so a client's own width is honoured.
"""

from pathlib import Path

SRC = Path(__file__).resolve().parents[2] / "src" / "bastproxy"
OWNER = "plugins/core/proxy/plugin/_proxy.py"


def test_linelen_literal_only_in_the_proxy_plugin() -> None:
    offenders = sorted(
        path.relative_to(SRC).as_posix()
        for path in SRC.rglob("*.py")
        if '"linelen"' in path.read_text(encoding="utf-8")
        and path.relative_to(SRC).as_posix() != OWNER
    )
    assert offenders == []
