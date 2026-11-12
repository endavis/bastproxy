"""Tests for the dependabot configuration in ``.github/dependabot.yml``.

These tests are structural asserts on the parsed YAML. They do not run
dependabot -- they only verify the config's shape.

The guarantee that matters here is the ``codeql-action`` group (issue #799).
``github/codeql-action/init`` and ``github/codeql-action/analyze`` are two
separate dependencies to dependabot but a single unit to CodeQL: ``init``
writes a config file stamped with its own version, and ``analyze`` refuses to
load a config written by a different one::

    Loaded a configuration file for version '4.37.8', but running version '4.37.9'

Ungrouped, dependabot opens one PR per sub-action, each bumping only half the
pair. Both fail, and neither can be merged to unblock the other -- that is
exactly what happened to PRs #794 and #795. The group is what prevents it, so
its removal must be a CI failure rather than a silent return to split PRs.

The companion assert lives in ``tests/test_codeql_workflow.py``, which checks
that the two actions are in fact pinned to the same SHA today.
"""

from __future__ import annotations

import json
import re
import tomllib
from pathlib import Path
from typing import Any

import yaml

CONFIG_PATH = Path(__file__).parent.parent / ".github" / "dependabot.yml"

AUTOMERGE_CONFIG_PATH = Path(__file__).parent.parent / ".github" / "automerge-config.json"
CATCH_ALL_GROUP = "minor-and-patch"

# The two halves of the CodeQL action that must always bump together.
CODEQL_SUBACTIONS = ("github/codeql-action/init", "github/codeql-action/analyze")


def _load_config() -> dict[str, Any]:
    """Load and parse the dependabot config YAML.

    The explicit ``encoding="utf-8"`` is required for Windows, where the
    default ``locale.getpreferredencoding()`` is cp1252 and chokes on any
    non-ASCII content in the file (lesson from issue #430).
    """
    # Bind to an annotated local first: yaml.safe_load returns Any,
    # and returning Any from a typed function trips warn_return_any.
    data: dict[str, Any] = yaml.safe_load(CONFIG_PATH.read_text(encoding="utf-8"))
    return data


def _github_actions_block() -> dict[str, Any]:
    """Return the ``github-actions`` ecosystem entry from ``updates``."""
    config = _load_config()
    updates: list[dict[str, Any]] = config["updates"]
    block = next(u for u in updates if u.get("package-ecosystem") == "github-actions")
    return block


def _glob_matches(pattern: str, name: str) -> bool:
    """Return True if a dependabot group glob matches a dependency name.

    Dependabot group patterns use ``*`` as the only wildcard and match the
    whole name. Everything else is escaped so a ``.`` in a pattern cannot
    silently behave as "any character".
    """
    escaped = re.escape(pattern).replace(r"\*", ".*")
    return re.fullmatch(escaped, name) is not None


class TestConfigFile:
    """The config file exists and parses as YAML."""

    def test_config_file_exists(self) -> None:
        """The dependabot config should exist."""
        assert CONFIG_PATH.exists(), f"Config not found: {CONFIG_PATH}"

    def test_config_parses_as_yaml(self) -> None:
        """The config should be valid YAML with a version and updates list."""
        config = _load_config()
        assert config["version"] == 2
        assert isinstance(config["updates"], list)

    def test_has_github_actions_ecosystem(self) -> None:
        """A ``github-actions`` ecosystem block must be configured."""
        assert _github_actions_block()["directory"] == "/"


class TestCodeqlActionGroup:
    """The CodeQL sub-actions must bump as one PR.

    This is the core regression guard for issue #799. Do NOT remove the group
    without also removing the reason it exists.
    """

    def test_github_actions_block_defines_groups(self) -> None:
        """The ``github-actions`` ecosystem must define at least one group."""
        groups = _github_actions_block().get("groups")
        assert isinstance(groups, dict) and groups, (
            "the github-actions ecosystem must define a 'groups' block -- "
            "without it dependabot splits codeql-action into failing PRs (#799)"
        )

    def test_both_codeql_subactions_land_in_one_group(self) -> None:
        """``init`` and ``analyze`` must be matched by the *same* group.

        Asserted behaviorally rather than by literal pattern string: any
        pattern that captures both sub-actions satisfies the invariant, so a
        reasonable rewording of the glob does not become a false failure.
        """
        groups: dict[str, Any] = _github_actions_block().get("groups", {})

        matching = [
            name
            for name, spec in groups.items()
            if all(
                any(_glob_matches(p, sub) for p in spec.get("patterns", []))
                for sub in CODEQL_SUBACTIONS
            )
        ]

        assert matching, (
            "no dependabot group matches both "
            f"{CODEQL_SUBACTIONS[0]} and {CODEQL_SUBACTIONS[1]}; they will be "
            "bumped in separate PRs and CodeQL will fail with 'Loaded a "
            "configuration file for version X, but running version Y' (#799)"
        )

    def test_no_group_splits_the_codeql_subactions(self) -> None:
        """No group may claim one sub-action without claiming the other.

        A group matching only ``init`` would pull it into a grouped PR and
        leave ``analyze`` in a lone PR -- reintroducing the exact split the
        group exists to prevent.
        """
        groups: dict[str, Any] = _github_actions_block().get("groups", {})

        for name, spec in groups.items():
            patterns = spec.get("patterns", [])
            matched = [s for s in CODEQL_SUBACTIONS if any(_glob_matches(p, s) for p in patterns)]
            assert len(matched) != 1, (
                f"dependabot group {name!r} matches {matched[0]} but not the "
                "other codeql-action sub-action; the pair must bump together (#799)"
            )


def _ecosystem_block(ecosystem: str) -> dict[str, Any]:
    """Return the ``updates`` entry for a package ecosystem."""
    updates: list[dict[str, Any]] = _load_config()["updates"]
    return next(u for u in updates if u.get("package-ecosystem") == ecosystem)


class TestCatchAllGroup:
    """The minor/patch catch-all group that batches weekly updates (issue #1221)."""

    ECOSYSTEMS = ("uv", "github-actions")

    def test_each_ecosystem_has_catch_all(self) -> None:
        """Each ecosystem batches minor and patch bumps into one group."""
        for eco in self.ECOSYSTEMS:
            spec = _ecosystem_block(eco)["groups"][CATCH_ALL_GROUP]
            assert spec["patterns"] == ["*"], eco
            assert spec["update-types"] == ["minor", "patch"], eco

    # (ecosystem, group) pairs whose exclude-patterns must equal
    # sensitive_dependencies. ``codeql-action`` is left off: its only pattern,
    # ``github/codeql-action*``, can never match a sensitive glob.
    SENSITIVE_PARITY_GROUPS = (
        ("uv", "dev-dependencies"),
        ("uv", CATCH_ALL_GROUP),
        ("github-actions", CATCH_ALL_GROUP),
    )

    def test_groups_exclude_exactly_the_sensitive_dependencies(self) -> None:
        """exclude-patterns must equal ``sensitive_dependencies`` (no drift)."""
        sensitive: list[str] = json.loads(AUTOMERGE_CONFIG_PATH.read_text(encoding="utf-8"))[
            "sensitive_dependencies"
        ]
        assert sensitive
        for eco, group in self.SENSITIVE_PARITY_GROUPS:
            spec = _ecosystem_block(eco)["groups"][group]
            assert spec["exclude-patterns"] == sensitive, (
                f"{eco}/{group}: exclude-patterns drifted from sensitive_dependencies in "
                "automerge-config.json; a sensitive bump would hold the whole batch"
            )

    def test_catch_all_is_last_group(self) -> None:
        """A dependency matching several groups goes to the first listed.

        So the catch-all must come after the specific groups, or it swallows them.
        """
        for eco in self.ECOSYSTEMS:
            names = list(_ecosystem_block(eco)["groups"])
            assert names[-1] == CATCH_ALL_GROUP, f"{eco}: catch-all must be last, got {names}"

    def test_codeql_precedes_catch_all(self) -> None:
        """``codeql-action`` is listed before the catch-all so the pair bumps together."""
        names = list(_github_actions_block()["groups"])
        assert names.index("codeql-action") < names.index(CATCH_ALL_GROUP)

    def test_uv_dev_dependencies_precede_catch_all(self) -> None:
        """``dev-dependencies`` keeps its members ahead of the catch-all."""
        names = list(_ecosystem_block("uv")["groups"])
        assert names.index("dev-dependencies") < names.index(CATCH_ALL_GROUP)


class TestSemverUnclassifiableUpdates:
    """Updates the catch-all cannot take live in ``dev-dependencies`` (issue #1231).

    The catch-all has ``update-types``, so dependabot-core refuses to group a
    bump that changes only the fourth version component (type stubs) or has no
    locked version (``[build-system] requires``). ``dev-dependencies`` has no
    ``update-types`` and takes them instead.
    """

    @staticmethod
    def _dev_group() -> dict[str, Any]:
        group: dict[str, Any] = _ecosystem_block("uv")["groups"]["dev-dependencies"]
        return group

    def _matches_dev_patterns(self, name: str) -> bool:
        return any(_glob_matches(p, name) for p in self._dev_group()["patterns"])

    def test_dev_dependencies_has_no_update_types(self) -> None:
        """Without ``update-types`` dependabot skips the semver grouping check."""
        assert "update-types" not in self._dev_group()

    def test_type_stub_joins_dev_dependencies(self) -> None:
        """``types-pyyaml`` (``6.0.12.20260906`` -> ``6.0.12.20261030``) is grouped."""
        assert self._matches_dev_patterns("types-pyyaml")

    def test_build_system_requires_join_dev_dependencies(self) -> None:
        """Every ``[build-system] requires`` entry is grouped."""
        pyproject = Path(__file__).parent.parent / "pyproject.toml"
        data = tomllib.loads(pyproject.read_text(encoding="utf-8"))
        requires: list[str] = data["build-system"]["requires"]
        assert requires
        for req in requires:
            match = re.match(r"[A-Za-z0-9._-]+", req)
            assert match, req
            name = match.group(0).lower()
            assert self._matches_dev_patterns(name), (
                f"build requirement {name!r} would arrive as its own PR (#1231)"
            )

    def test_sensitive_type_stub_is_excluded(self) -> None:
        """``types-*`` must not pull a sensitive stub such as types-pyOpenSSL in.

        The name is lowercase because dependabot reports PEP 503 normalized
        names. ``_glob_matches`` stays case-sensitive: the CodeQL tests rely on it.
        """
        excludes = self._dev_group()["exclude-patterns"]
        assert any(_glob_matches(p, "types-pyopenssl") for p in excludes)
