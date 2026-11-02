"""Tests for the pure helpers behind `doit issue --upstream` (#1090)."""

from __future__ import annotations

from pathlib import Path

import pytest

from tools.doit.upstream import (
    PRIVATE_REPORT_URL,
    SETTINGS_RELATIVE,
    TEMPLATE_REPO,
    build_footer,
    is_template_repo_slug,
    read_recorded_commit,
    security_match,
)

REPO_ROOT = Path(__file__).resolve().parents[2]


def _write_settings(root: Path, text: str) -> None:
    path = root / SETTINGS_RELATIVE
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


class TestReadRecordedCommit:
    def test_reads_the_commit(self, tmp_path: Path) -> None:
        _write_settings(tmp_path, '[template]\ncommit = "  abc1234  "\n')
        assert read_recorded_commit(tmp_path) == "abc1234"

    def test_missing_file(self, tmp_path: Path) -> None:
        assert read_recorded_commit(tmp_path) is None

    def test_invalid_toml(self, tmp_path: Path) -> None:
        _write_settings(tmp_path, "not = [valid")
        assert read_recorded_commit(tmp_path) is None

    @pytest.mark.parametrize(
        "text",
        [
            'template = "x"\n',
            "[other]\nx = 1\n",
            "[template]\ncommit = 5\n",
            '[template]\ncommit = " "\n',
        ],
    )
    def test_unusable_shapes(self, tmp_path: Path, text: str) -> None:
        _write_settings(tmp_path, text)
        assert read_recorded_commit(tmp_path) is None


class TestIsTemplateRepoSlug:
    @pytest.mark.parametrize("slug", [TEMPLATE_REPO, TEMPLATE_REPO.upper(), f" {TEMPLATE_REPO}\n"])
    def test_matches_case_insensitively(self, slug: str) -> None:
        assert is_template_repo_slug(slug)

    @pytest.mark.parametrize("slug", ["", "someone/pyproject-template", f"{TEMPLATE_REPO}-fork"])
    def test_other_slugs(self, slug: str) -> None:
        assert not is_template_repo_slug(slug)


class TestSecurityMatch:
    @pytest.mark.parametrize(
        "text",
        [
            "a vulnerability in the hook",
            "VULNERABLE hook",
            "exploitable path",
            "see CVE-2026-1234",
            "GHSA-abcd-efgh",
            "a security issue",
            "security advisory",
            "hook bypass via redirect",
            "privilege escalation",
            "remote code execution",
            "arbitrary command runs",
            "shell injection",
            "path traversal",
            "token leaked",
            "secrets exposed",
            "credentials disclosed",
        ],
    )
    def test_refuses_in_title_and_body(self, text: str) -> None:
        assert security_match(text, "") is not None
        assert security_match("title", f"body {text} body") is not None

    @pytest.mark.parametrize(
        "text",
        [
            "security-triage skill crashes",
            "doit audit fails",
            "the security extra is missing",
            "doit security prints nothing",
        ],
    )
    def test_allows_ordinary_bugs(self, text: str) -> None:
        assert security_match(text, text) is None

    def test_returns_the_matched_term(self) -> None:
        assert security_match("t", "found a Path Traversal here") == "Path Traversal"


class TestBuildFooter:
    def test_with_commit(self) -> None:
        footer = build_footer("abc1234")
        assert footer.startswith("---\n")
        assert "Template commit: `abc1234`" in footer
        assert "Origin" not in footer

    def test_without_commit(self) -> None:
        assert "Template commit: `not recorded`" in build_footer(None)

    def test_origin_only_when_given(self) -> None:
        assert "Origin: `me/private`" in build_footer("abc", "me/private")


def test_private_report_url_points_at_the_policy() -> None:
    assert f"https://github.com/{TEMPLATE_REPO}/security/policy" == PRIVATE_REPORT_URL


def test_template_repo_name_appears_in_one_doit_module() -> None:
    """The name lives once in `tools/doit/` (#1090); other modules import it."""
    holders = [
        path.name
        for path in sorted((REPO_ROOT / "tools" / "doit").glob("*.py"))
        if TEMPLATE_REPO in path.read_text(encoding="utf-8")
    ]
    assert holders == ["upstream.py"]
