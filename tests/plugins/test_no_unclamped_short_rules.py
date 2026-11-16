"""No page layout code draws a bare 40/50/60-wide rule or header (#508).

The shorter rules clamp with ``min(N, plugins.core.proxy:line.length.get())`` so a narrow client
is not overflowed.
"""

import re
from pathlib import Path

SRC = Path(__file__).resolve().parents[2] / "src" / "bastproxy"

PATTERNS = [
    re.compile(r"""["']-["'] \* (40|50|60)\b"""),
    re.compile(r"""["']-["'],\s*(40|50|60)\b"""),
]


def _matches(text: str) -> bool:
    return any(p.search(text) for p in PATTERNS)


def test_guard_regexes_catch_known_forms() -> None:
    for sample in ('"-" * 60', "'-' * 40", '("x", "-", 50,', '"-",\n    60,'):
        assert _matches(sample), sample


def test_no_unclamped_short_rules_in_src() -> None:
    offenders = sorted(
        path.relative_to(SRC).as_posix()
        for path in SRC.rglob("*.py")
        if _matches(path.read_text(encoding="utf-8"))
    )
    assert offenders == []
