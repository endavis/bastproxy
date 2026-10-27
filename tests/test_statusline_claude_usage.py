"""Tests for tools/statusline/claude-usage.sh opt-in helper."""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path

import pytest

# The helper is a bash script targeting Linux/macOS; the Windows GitHub Actions
# runner's `bash` resolves to wsl.exe (which has no installed distribution),
# so subprocess invocations cannot exercise the real shell behavior.
pytestmark = pytest.mark.skipif(
    sys.platform == "win32",
    reason="bash helper is Linux/macOS only; Windows runner has no usable bash",
)

REPO_ROOT = Path(__file__).resolve().parent.parent
SCRIPT = REPO_ROOT / "tools" / "statusline" / "claude-usage.sh"
STATUSLINE = REPO_ROOT / ".claude" / "statusline-command.sh"

_STATUSLINE_INPUT = json.dumps(
    {
        "model": {"display_name": "Claude"},
        "cwd": "/tmp",
        "transcript_path": "",
        "context_window": {"context_window_size": 200000},
    }
)

# ISO timestamps far in the future so the test is timezone-agnostic for the date
# part; only HHMM can vary by local TZ offset and that is accepted by the regex.
_FH_RESETS_AT = "2099-06-15T18:00:00+00:00"
_WK_RESETS_AT = "2099-06-16T20:00:00+00:00"


def _make_env(tmp_path: Path) -> dict[str, str]:
    """Build a minimal, network-safe environment for subprocess calls."""
    cache_dir = tmp_path / "cache"
    cache_dir.mkdir()
    creds_dir = tmp_path / "creds"
    creds_dir.mkdir()
    return {
        "HOME": str(tmp_path),
        "XDG_CACHE_HOME": str(cache_dir),
        "CLAUDE_CONFIG_DIR": str(creds_dir),
        "PATH": os.environ["PATH"],
    }


def test_script_exists_and_executable() -> None:
    """Helper script must exist at the expected path and be executable."""
    assert SCRIPT.exists(), f"Script not found: {SCRIPT}"
    assert os.access(SCRIPT, os.X_OK), f"Script not executable: {SCRIPT}"


def test_script_syntax_valid() -> None:
    """bash -n must report no syntax errors."""
    result = subprocess.run(
        ["bash", "-n", str(SCRIPT)],
        capture_output=True,
        text=True,
        timeout=5,
    )
    assert result.returncode == 0, f"Syntax error:\n{result.stderr}"


def test_emits_fallback_when_credentials_missing(tmp_path: Path) -> None:
    """No .credentials.json and no cache -> output is literal '?', exit 0."""
    env = _make_env(tmp_path)
    result = subprocess.run(
        ["bash", str(SCRIPT)],
        env=env,
        capture_output=True,
        text=True,
        timeout=5,
    )
    assert result.returncode == 0
    assert result.stdout.strip() == "?"


def test_uses_fresh_cache_skips_network(tmp_path: Path) -> None:
    """Pre-seeded fresh cache is parsed and returned without hitting the network."""
    env = _make_env(tmp_path)
    cache_file = Path(env["XDG_CACHE_HOME"]) / "claude-usage.json"
    payload = {
        "five_hour": {"utilization": 42.7, "resets_at": _FH_RESETS_AT},
        "seven_day": {"utilization": 7.3, "resets_at": _WK_RESETS_AT},
    }
    cache_file.write_text(json.dumps(payload), encoding="utf-8")
    # Ensure mtime is current (fresh cache)
    now = time.time()
    os.utime(cache_file, (now, now))

    result = subprocess.run(
        ["bash", str(SCRIPT)],
        env=env,
        capture_output=True,
        text=True,
        timeout=5,
    )
    assert result.returncode == 0
    output = result.stdout.strip()
    # Format: 5h:42%@HHMM wk:7%@aaa-HHMM  (HHMM and aaa vary by runner TZ)
    assert re.search(r"5h:42%@\d{4} wk:7%@[A-Za-z]{3}-\d{4}", output), (
        f"Unexpected output: {output!r}"
    )


def test_emits_fallback_on_malformed_cache(tmp_path: Path) -> None:
    """Fresh cache that contains invalid JSON emits '?'."""
    env = _make_env(tmp_path)
    cache_file = Path(env["XDG_CACHE_HOME"]) / "claude-usage.json"
    cache_file.write_text("not-json", encoding="utf-8")
    now = time.time()
    os.utime(cache_file, (now, now))
    # No credentials file either, so the script won't fall through to the network

    result = subprocess.run(
        ["bash", str(SCRIPT)],
        env=env,
        capture_output=True,
        text=True,
        timeout=5,
    )
    assert result.returncode == 0
    assert result.stdout.strip() == "?"


def test_emits_fallback_when_token_field_missing(tmp_path: Path) -> None:
    """Credentials file present but missing claudeAiOauth.accessToken -> '?'."""
    env = _make_env(tmp_path)
    creds_file = Path(env["CLAUDE_CONFIG_DIR"]) / ".credentials.json"
    creds_file.write_text(json.dumps({}), encoding="utf-8")

    result = subprocess.run(
        ["bash", str(SCRIPT)],
        env=env,
        capture_output=True,
        text=True,
        timeout=5,
    )
    assert result.returncode == 0
    assert result.stdout.strip() == "?"


def test_emits_fallback_when_resets_at_missing(tmp_path: Path) -> None:
    """Fresh cache with utilization but no resets_at fields emits '?'."""
    env = _make_env(tmp_path)
    cache_file = Path(env["XDG_CACHE_HOME"]) / "claude-usage.json"
    payload = {
        "five_hour": {"utilization": 42.7},
        "seven_day": {"utilization": 7.3},
    }
    cache_file.write_text(json.dumps(payload), encoding="utf-8")
    now = time.time()
    os.utime(cache_file, (now, now))

    result = subprocess.run(
        ["bash", str(SCRIPT)],
        env=env,
        capture_output=True,
        text=True,
        timeout=5,
    )
    assert result.returncode == 0
    assert result.stdout.strip() == "?"


def test_null_resets_at_shows_placeholder_time(tmp_path: Path) -> None:
    """resets_at: null (no active window) shows -- for that bucket, not '?'."""
    env = _make_env(tmp_path)
    cache_file = Path(env["XDG_CACHE_HOME"]) / "claude-usage.json"
    payload = {
        "five_hour": {"utilization": 0.0, "resets_at": None},
        "seven_day": {"utilization": 18.0, "resets_at": _WK_RESETS_AT},
    }
    cache_file.write_text(json.dumps(payload), encoding="utf-8")
    now = time.time()
    os.utime(cache_file, (now, now))

    result = subprocess.run(
        ["bash", str(SCRIPT)],
        env=env,
        capture_output=True,
        text=True,
        timeout=5,
    )
    assert result.returncode == 0
    output = result.stdout.strip()
    assert re.fullmatch(r"5h:0%@-- wk:18%@[A-Za-z]{3}-\d{4}", output), (
        f"Unexpected output: {output!r}"
    )


def test_both_resets_at_null_shows_placeholders(tmp_path: Path) -> None:
    """Both buckets without an active window still emit the segment."""
    env = _make_env(tmp_path)
    cache_file = Path(env["XDG_CACHE_HOME"]) / "claude-usage.json"
    payload = {
        "five_hour": {"utilization": 0.0, "resets_at": None},
        "seven_day": {"utilization": 0.0, "resets_at": None},
    }
    cache_file.write_text(json.dumps(payload), encoding="utf-8")
    now = time.time()
    os.utime(cache_file, (now, now))

    result = subprocess.run(
        ["bash", str(SCRIPT)],
        env=env,
        capture_output=True,
        text=True,
        timeout=5,
    )
    assert result.returncode == 0
    assert result.stdout.strip() == "5h:0%@-- wk:0%@--"


def test_statusline_shows_usage_when_five_hour_window_inactive(tmp_path: Path) -> None:
    """A null 5h resets_at must not hide the weekly gauge in the statusline."""
    env = _make_env(tmp_path)
    env["CLAUDE_USAGE_STATUSLINE"] = "1"
    env["CLAUDE_PROJECT_DIR"] = str(REPO_ROOT)
    cache_file = Path(env["XDG_CACHE_HOME"]) / "claude-usage.json"
    payload = {
        "five_hour": {"utilization": 0.0, "resets_at": None},
        "seven_day": {"utilization": 18.0, "resets_at": _WK_RESETS_AT},
    }
    cache_file.write_text(json.dumps(payload), encoding="utf-8")
    now = time.time()
    os.utime(cache_file, (now, now))

    result = subprocess.run(
        ["bash", str(STATUSLINE)],
        input=_STATUSLINE_INPUT,
        env=env,
        capture_output=True,
        text=True,
        timeout=10,
    )
    assert result.returncode == 0, f"stderr: {result.stderr}"
    plain = re.sub(r"\x1b\[[0-9;]*m", "", result.stdout)
    assert re.search(r"5h:0%@-- · wk:18%@[A-Za-z]{3}-\d{4}", plain), f"Unexpected output: {plain!r}"


def test_emits_fallback_when_resets_at_malformed(tmp_path: Path) -> None:
    """Fresh cache with unparsable resets_at string emits '?'."""
    env = _make_env(tmp_path)
    cache_file = Path(env["XDG_CACHE_HOME"]) / "claude-usage.json"
    payload = {
        "five_hour": {"utilization": 42.7, "resets_at": "not-a-date"},
        "seven_day": {"utilization": 7.3, "resets_at": "also-not-a-date"},
    }
    cache_file.write_text(json.dumps(payload), encoding="utf-8")
    now = time.time()
    os.utime(cache_file, (now, now))

    result = subprocess.run(
        ["bash", str(SCRIPT)],
        env=env,
        capture_output=True,
        text=True,
        timeout=5,
    )
    assert result.returncode == 0
    assert result.stdout.strip() == "?"


def _seed_fresh_cache(env: dict[str, str]) -> None:
    """Pre-write a parseable, fresh cache so the helper short-circuits curl."""
    cache_file = Path(env["XDG_CACHE_HOME"]) / "claude-usage.json"
    payload = {
        "five_hour": {"utilization": 42.7, "resets_at": _FH_RESETS_AT},
        "seven_day": {"utilization": 7.3, "resets_at": _WK_RESETS_AT},
    }
    cache_file.write_text(json.dumps(payload), encoding="utf-8")
    now = time.time()
    os.utime(cache_file, (now, now))


def test_statusline_invokes_helper_when_env_set(tmp_path: Path) -> None:
    """With CLAUDE_USAGE_STATUSLINE=1 and a fresh cache, statusline shows usage."""
    env = _make_env(tmp_path)
    env["CLAUDE_USAGE_STATUSLINE"] = "1"
    env["CLAUDE_PROJECT_DIR"] = str(REPO_ROOT)
    _seed_fresh_cache(env)

    result = subprocess.run(
        ["bash", str(STATUSLINE)],
        input=_STATUSLINE_INPUT,
        env=env,
        capture_output=True,
        text=True,
        timeout=10,
    )
    assert result.returncode == 0, f"stderr: {result.stderr}"
    # Both bucket labels must appear; exact times vary by runner TZ.
    # The wrapper injects a middle-dot separator between gauges.
    assert "5h:" in result.stdout
    assert "wk:" in result.stdout
    assert "7d:" not in result.stdout
    assert " · " in result.stdout


def test_statusline_skips_helper_when_env_unset(tmp_path: Path) -> None:
    """Without CLAUDE_USAGE_STATUSLINE, statusline never invokes the helper."""
    env = _make_env(tmp_path)
    env["CLAUDE_PROJECT_DIR"] = str(REPO_ROOT)
    # Fresh cache exists, so a bug that skipped the env check would still surface usage.
    _seed_fresh_cache(env)

    result = subprocess.run(
        ["bash", str(STATUSLINE)],
        input=_STATUSLINE_INPUT,
        env=env,
        capture_output=True,
        text=True,
        timeout=10,
    )
    assert result.returncode == 0, f"stderr: {result.stderr}"
    assert "5h:" not in result.stdout
    assert "wk:" not in result.stdout
