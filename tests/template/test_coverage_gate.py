"""Contract tests for the enforced coverage gate.

The gate previously measured only ``src/package_name/`` — a 66-statement
skeleton that every downstream project deletes — while several thousand
statements of `tools/` went unmeasured. These tests pin the scope so that
narrowing it back is a deliberate, visible change rather than a silent one.

See ``docs/development/ci-cd-testing.md`` for the template/downstream split.
"""

from __future__ import annotations

import re
import tomllib
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]
PYPROJECT = REPO_ROOT / "pyproject.toml"
CI_WORKFLOW = REPO_ROOT / ".github" / "workflows" / "ci.yml"
DOIT_TESTING = REPO_ROOT / "tools" / "doit" / "testing.py"


def _coverage_config() -> dict[str, Any]:
    """Return the ``[tool.coverage]`` table from pyproject.toml."""
    with PYPROJECT.open("rb") as fh:
        data: dict[str, Any] = tomllib.load(fh)
    config: dict[str, Any] = data["tool"]["coverage"]
    return config


def test_gate_measures_both_the_package_and_tools() -> None:
    """`tools/` is in scope, not just the replaceable package skeleton."""
    source = _coverage_config()["run"]["source"]
    assert "tools" in source, (
        "tools/ runs releases, PRs and the dangerous-command hook; it must be measured"
    )

    # The package entry is `package_name` here and the real package name in a
    # spawned project, because configure.py rewrites it. Assert that it resolves
    # to a package rather than pinning the placeholder, so this test keeps
    # working downstream (#731).
    packages = [entry for entry in source if entry != "tools"]
    assert packages, "the project's own package must be measured alongside tools/"
    for pkg in packages:
        assert (REPO_ROOT / "src" / pkg).is_dir(), (
            f"coverage source {pkg!r} is not a package under src/"
        )


def test_template_management_suite_is_out_of_scope() -> None:
    """`tools/pyproject_template/` must stay omitted from the gate.

    It is the one part of `tools/` that does not ship to the spawned project:
    ADR-9017 makes its tests template-owned and both spawn routes delete the
    suite itself. Measuring it means measuring code that is never tested
    downstream, which put a spawned project 19 points under the gate (#731).

    Dropping the omit re-breaks that shape silently — the template's own number
    would still pass, because here the suite *is* tested.
    """
    omit = _coverage_config()["run"].get("omit", [])
    assert "tools/pyproject_template/*" in omit, (
        "tools/pyproject_template/* must stay in [tool.coverage.run] omit so the "
        "gate measures the same code in the template and in a spawned project"
    )


def test_shipped_tooling_is_not_omitted() -> None:
    """The omit must not be widened to the tooling the spawned project runs."""
    omit = _coverage_config()["run"].get("omit", [])
    for shipped in ("tools/doit", "tools/hooks"):
        offenders = [pattern for pattern in omit if pattern.startswith(shipped)]
        assert not offenders, (
            f"{offenders} would drop {shipped}/ from the gate. That code ships to "
            "and runs in the spawned project; it must stay measured."
        )


def test_threshold_is_enforced_and_not_aspirational() -> None:
    """`fail_under` must be a real gate, not a number aimed at the wrong target.

    A high threshold over a tiny scope is trivially met and measures nothing.
    This asserts the gate is set at all and is not pointed above what the
    combined scope achieves; the paired scope assertion above keeps it honest.
    """
    report = _coverage_config()["report"]
    assert "fail_under" in report, "the coverage gate must be enforced"
    assert 0 < report["fail_under"] <= 100


def test_coverage_invocations_are_config_driven() -> None:
    """Neither `doit coverage` nor CI may hardcode the scope on the command line.

    A `--cov=<name>` flag overrides `[tool.coverage.run] source`, so a stale
    flag silently narrows the gate while pyproject.toml still looks correct.
    Hardcoding the template's own package name is worse still: placeholder
    replacement does not rewrite every file, so a renamed project ends up
    measuring a module that no longer exists (#684). A bare `--cov` enables
    coverage and defers to the configured source.
    """
    for path in (DOIT_TESTING, CI_WORKFLOW):
        text = path.read_text(encoding="utf-8")
        # `--cov-report=` / `--cov-fail-under=` use a hyphen, so this only
        # matches scope flags.
        scopes = re.findall(r"--cov=([\w./-]+)", text)
        assert not scopes, (
            f"{path.name} hardcodes coverage scope {scopes}; use a bare --cov "
            f"so [tool.coverage.run] source drives it"
        )
        assert "--cov" in text, f"{path.name} must still enable coverage"
