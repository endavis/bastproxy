"""The seven places the supported Python versions are declared must agree (#833).

Each consumer reads its own copy: `uv`/pip read `requires-python` in `pyproject.toml`,
ruff reads `[tool.ruff] target-version`, mypy reads `[tool.mypy] python_version`,
pyright reads `[tool.pyright] pythonVersion`, `uv` also reads `.python-version`, and
CI builds its test matrix from `.github/python-versions.json` (`oldest`/`newest`,
via `.github/actions/python-versions/action.yml`). The PyPI classifiers are a
seventh, independent declaration: nothing in this repository reads them back,
only PyPI itself, once the package is published.

Change one without the others and the tools check against different Pythons. This
file is the check nothing else provided: no test referenced `requires-python`, and
none compared `.github/python-versions.json` with `pyproject.toml`.

Ships downstream: every file this test reads is downstream-owned config, not
template scaffolding — none of `pyproject.toml`, `.python-version`, or
`.github/python-versions.json` appears in `SETUP_FILES`, `ALL_TEMPLATE_FILES`, or
`ALL_TEMPLATE_DIRS` in `tools/pyproject_template/cleanup.py`. It imports neither
the package nor `tools/`, so it needs no entry in `[tool.mutmut]
pytest_add_cli_args_test_selection` (#873) and runs unmodified in a spawned
project.
"""

from __future__ import annotations

import json
import re
import tomllib
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parent.parent
PYPROJECT = REPO_ROOT / "pyproject.toml"
PYTHON_VERSION_FILE = REPO_ROOT / ".python-version"
VERSIONS_JSON = REPO_ROOT / ".github" / "python-versions.json"

# The label a mismatch is reported under for each of the six sources that state
# a single floor version. `requires-python` is the reference: it is the value
# pip/uv actually enforce, and every other source exists to agree with it.
REFERENCE_LABEL = "requires-python"


def _pyproject() -> dict[str, Any]:
    with PYPROJECT.open("rb") as f:
        return tomllib.load(f)


def _versions_json() -> dict[str, str]:
    data: dict[str, str] = json.loads(VERSIONS_JSON.read_text(encoding="utf-8"))
    return data


def _floor_from_requires_python(spec: str) -> str:
    """Return the `X.Y` floor out of a `requires-python` spec like `">=3.12"`."""
    match = re.search(r"(\d+\.\d+)", spec)
    if not match:
        raise ValueError(f"no version found in requires-python {spec!r}")
    return match.group(1)


def _floor_from_ruff_target(target: str) -> str:
    """Return the `X.Y` floor out of a ruff `target-version` like `"py312"`."""
    match = re.fullmatch(r"py3(\d+)", target)
    if not match:
        raise ValueError(f"unrecognized ruff target-version {target!r}")
    return f"3.{match.group(1)}"


def _current_floors() -> dict[str, str]:
    """Return this repository's six floor-stating settings, label -> `X.Y`."""
    config = _pyproject()
    return {
        REFERENCE_LABEL: _floor_from_requires_python(config["project"]["requires-python"]),
        "ruff target-version": _floor_from_ruff_target(config["tool"]["ruff"]["target-version"]),
        "mypy python_version": config["tool"]["mypy"]["python_version"],
        "pyright pythonVersion": config["tool"]["pyright"]["pythonVersion"],
        ".python-version": PYTHON_VERSION_FILE.read_text(encoding="utf-8").strip(),
        "python-versions.json oldest": _versions_json()["oldest"],
    }


def _floor_disagreements(floors: dict[str, str]) -> list[str]:
    """Return the labels in *floors* whose version differs from `requires-python`'s.

    *floors* must carry a `REFERENCE_LABEL` entry; the other keys are free-form
    so a caller can feed in a subset or a synthetic fixture.
    """
    reference = floors[REFERENCE_LABEL]
    return sorted(label for label, version in floors.items() if version != reference)


def _classifier_versions(classifiers: list[str]) -> list[str]:
    """Return the `X.Y` versions named by `Programming Language :: Python :: X.Y`.

    Excludes the bare `Programming Language :: Python :: 3` classifier, which
    names no specific minor version.
    """
    versions = []
    for classifier in classifiers:
        match = re.fullmatch(r"Programming Language :: Python :: (3\.\d+)", classifier)
        if match:
            versions.append(match.group(1))
    return versions


def _expected_classifier_range(oldest: str, newest: str) -> list[str]:
    """Return the `X.Y` versions `oldest` through `newest` should cover, inclusive."""
    oldest_minor = int(oldest.split(".")[1])
    newest_minor = int(newest.split(".")[1])
    return [f"3.{minor}" for minor in range(oldest_minor, newest_minor + 1)]


def _classifier_mismatch(classifiers: list[str], oldest: str, newest: str) -> str | None:
    """Return a description of the mismatch, or None if *classifiers* cover exactly the range."""
    actual = _classifier_versions(classifiers)
    expected = _expected_classifier_range(oldest, newest)
    if actual == expected:
        return None
    return f"classifiers list {actual}, expected {expected} ({oldest} through {newest})"


def test_seven_settings_agree_on_the_current_tree() -> None:
    """`requires-python`, ruff, mypy, pyright, `.python-version` and `oldest` name one version."""
    disagreements = _floor_disagreements(_current_floors())

    assert not disagreements, (
        f"these settings disagree with {REFERENCE_LABEL}: {disagreements}. "
        "See the seven-settings list in this file's module docstring."
    )


def test_classifiers_cover_oldest_through_newest_on_the_current_tree() -> None:
    """The classifiers must list exactly `oldest` through `newest`, no gaps, no extras."""
    classifiers = _pyproject()["project"]["classifiers"]
    versions = _versions_json()

    mismatch = _classifier_mismatch(classifiers, versions["oldest"], versions["newest"])

    assert mismatch is None, mismatch


def test_floor_disagreement_scanner_detects_a_mismatch() -> None:
    """The scanner must catch a disagreement, not merely pass on our own settings.

    Synthetic, in-memory: one source (`pyright pythonVersion`) is bumped ahead of
    the rest, the way a partial floor-raise would leave it.
    """
    floors = {
        REFERENCE_LABEL: "3.12",
        "ruff target-version": "3.12",
        "mypy python_version": "3.12",
        "pyright pythonVersion": "3.13",
        ".python-version": "3.12",
        "python-versions.json oldest": "3.12",
    }

    assert _floor_disagreements(floors) == ["pyright pythonVersion"]


def test_floor_disagreement_scanner_passes_when_everything_agrees() -> None:
    """The scanner must not cry wolf on settings that do agree."""
    floors = {
        REFERENCE_LABEL: "3.13",
        "ruff target-version": "3.13",
        "mypy python_version": "3.13",
        "pyright pythonVersion": "3.13",
        ".python-version": "3.13",
        "python-versions.json oldest": "3.13",
    }

    assert _floor_disagreements(floors) == []


def test_classifier_scanner_detects_a_mismatch() -> None:
    """The classifier check must catch a missing version, not merely pass on ours.

    Synthetic: `newest` says 3.14, but the classifier for it was never added —
    the "add a newest version" half of a bump done incompletely.
    """
    classifiers = [
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.12",
        "Programming Language :: Python :: 3.13",
    ]

    mismatch = _classifier_mismatch(classifiers, oldest="3.12", newest="3.14")

    assert mismatch is not None
    assert "3.14" in mismatch


def test_classifier_scanner_passes_on_an_exact_range() -> None:
    """The classifier check must not cry wolf on a range that is already exact."""
    classifiers = [
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.12",
        "Programming Language :: Python :: 3.13",
        "Programming Language :: Python :: 3.14",
    ]

    assert _classifier_mismatch(classifiers, oldest="3.12", newest="3.14") is None


def test_floor_parsers_read_the_formats_each_tool_actually_writes() -> None:
    """Each parser must handle the literal syntax its tool uses, not a guess at it."""
    assert _floor_from_requires_python(">=3.12") == "3.12"
    assert _floor_from_ruff_target("py312") == "3.12"
    # A two-digit minor, to catch an off-by-one in the "py3" + minor split.
    assert _floor_from_ruff_target("py310") == "3.10"
