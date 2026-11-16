"""No page layout code hard-codes an 80/79-wide rule or header (#421).

Widths come from ``plugins.core.proxy:line.length.get`` so a client's own width is honoured.
"""

import re
from pathlib import Path

SRC = Path(__file__).resolve().parents[2] / "src" / "bastproxy"

PATTERNS = [
    re.compile(r"""["']-["'] \* (79|80)\b"""),
    re.compile(r"\b(line_)?length=80\b"),
    re.compile(r"\(\s*80\s*-\s*2\s*\)"),
    re.compile(r""", ["']=["'], 80\b"""),
]


def _matches(text: str) -> bool:
    return any(p.search(text) for p in PATTERNS)


def test_guard_regexes_catch_known_forms() -> None:
    for sample in ('"-" * 80', "'-' * 79", "length=80", "line_length=80", "(80 - 2)", ', "=", 80,'):
        assert _matches(sample), sample


def test_no_fixed_80_wide_output_in_src() -> None:
    offenders = sorted(
        f"{path.relative_to(SRC).as_posix()}:{n}"
        for path in SRC.rglob("*.py")
        for n, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1)
        if _matches(line)
    )
    assert offenders == []
