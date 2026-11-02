"""Tests for the agent_cmd doit task (role -> subagent / inline / cli resolution)."""

from __future__ import annotations

import json
import subprocess
from collections.abc import Callable
from pathlib import Path

import pytest

from tools.doit import agent_cmd as ac
from tools.doit.agent_cmd import (
    BASE_COMMANDS,
    AgentConfigError,
    RoleConfig,
    build_command,
    canonical_cli,
    check_models,
    load_role_configs,
    merge_layers,
    parse_layer,
    resolve,
    task_agent_cmd,
    user_config_path,
)

AGY_LIST = (
    "Fetching available models...\n"
    "gemini-4-argon-medium\tGemini 4 Argon (Medium)\n"
    "gemini-4-argon-high\tGemini 4 Argon (High)\n"
)
CODEX_LIST = json.dumps({"models": [{"slug": "gpt-6-luna"}, {"slug": "gpt-5.6-terra"}]})
COPILOT_LIST = (
    "  `logLevel`: log level\n\n"
    "  `model`: AI model to use for Copilot CLI\n"
    '    - "gpt-6.1-sol"\n'
    '    - "gemini-4-argon"\n\n'
    "  `contextTier`: tier\n"
    '    - "default"\n'
)


EXAMPLE_CONFIG = (
    Path(__file__).resolve().parents[2] / "docs" / "development" / "ai" / "agents.example.toml"
)


class TestExampleConfig:
    def test_example_parses_and_sets_every_role(self, tmp_path: Path) -> None:
        got = load_role_configs(EXAMPLE_CONFIG, tmp_path / "none.toml")
        assert set(got) == set(ac.ROLES)


class TestLayering:
    def test_no_files_is_empty(self, tmp_path: Path) -> None:
        assert load_role_configs(tmp_path / "u.toml", tmp_path / "l.toml") == {}

    def test_user_only(self, tmp_path: Path) -> None:
        u = tmp_path / "u.toml"
        u.write_text('[roles.review]\ncli = "agy"\nmodel = "m"\n')
        got = load_role_configs(u, tmp_path / "none.toml")
        assert got == {"review": RoleConfig("agy", "m")}

    def test_local_only(self, tmp_path: Path) -> None:
        lo = tmp_path / "l.toml"
        lo.write_text('[roles.code]\ncli = "antigravity"\n')
        assert load_role_configs(tmp_path / "none.toml", lo) == {"code": RoleConfig("agy")}

    def test_local_overrides_key_by_key(self) -> None:
        user = {"review": {"cli": "codex", "model": "a", "effort": "high"}}
        merged = merge_layers(user, {"review": {"model": "b"}})
        assert merged["review"] == {"cli": "codex", "model": "b", "effort": "high"}

    def test_local_cli_replaces_role(self) -> None:
        user = {"review": {"cli": "codex", "model": "a", "effort": "high"}}
        merged = merge_layers(user, {"review": {"cli": "agy"}})
        assert merged["review"] == {"cli": "agy"}

    def test_merge_does_not_mutate_inputs(self) -> None:
        user = {"review": {"cli": "codex"}}
        merge_layers(user, {"review": {"model": "x"}})
        assert user == {"review": {"cli": "codex"}}

    def test_xdg_path(self, tmp_path: Path) -> None:
        got = user_config_path({"XDG_CONFIG_HOME": str(tmp_path)}, tmp_path / "home")
        assert got == tmp_path / "pyproject-template" / "agents.toml"

    def test_home_fallback(self, tmp_path: Path) -> None:
        got = user_config_path({}, tmp_path)
        assert got == tmp_path / ".config" / "pyproject-template" / "agents.toml"


class TestConfigErrors:
    @pytest.mark.parametrize(
        "text",
        [
            "not = [toml",
            '[roles.nope]\ncli = "agy"\n',
            '[roles.review]\ncli = "agy"\nbogus = "x"\n',
            '[roles.review]\ncli = "gemini"\n',
            "[roles.review]\ncli = 3\n",
            '[roles.review]\ncli = "agy"\nmodel = "--evil"\n',
            '[other]\nx = "y"\n',
            '[roles]\nreview = "x"\n',
        ],
    )
    def test_parse_errors(self, text: str) -> None:
        with pytest.raises(AgentConfigError):
            parse_layer(text)

    @pytest.mark.parametrize("cli", ["claude", "agy"])
    def test_effort_rejected_off_codex_copilot(self, tmp_path: Path, cli: str) -> None:
        u = tmp_path / "u.toml"
        u.write_text(f'[roles.review]\ncli = "{cli}"\neffort = "high"\n')
        with pytest.raises(AgentConfigError, match="effort"):
            load_role_configs(u, tmp_path / "none.toml")

    def test_role_without_cli(self, tmp_path: Path) -> None:
        u = tmp_path / "u.toml"
        u.write_text('[roles.review]\nmodel = "x"\n')
        with pytest.raises(AgentConfigError, match="no cli"):
            load_role_configs(u, tmp_path / "none.toml")

    def test_unknown_cli_name(self) -> None:
        with pytest.raises(AgentConfigError):
            canonical_cli("nope")


class TestBuildCommand:
    @pytest.mark.parametrize("cli", list(BASE_COMMANDS))
    def test_no_config_is_todays_literal(self, cli: str) -> None:
        assert build_command(cli) == BASE_COMMANDS[cli]

    def test_antigravity_alias(self) -> None:
        assert build_command("antigravity") == BASE_COMMANDS["agy"]

    def test_agy_model(self) -> None:
        assert build_command("agy", "gemini-4-argon-high").endswith("--model gemini-4-argon-high")

    def test_claude_model(self) -> None:
        assert build_command("claude", "opus") == "claude -p '<prompt>' --model opus"

    def test_codex_model_and_effort_before_prompt(self) -> None:
        cmd = build_command("codex", "gpt-6-luna", "high")
        assert "exec -m gpt-6-luna -c model_reasoning_effort=high '<prompt>' < /dev/null" in cmd

    def test_copilot_model_and_effort(self) -> None:
        cmd = build_command("copilot", "gpt-6.1-sol", "high")
        assert cmd.endswith("--model gpt-6.1-sol --reasoning-effort high")

    def test_values_are_quoted(self) -> None:
        assert "'a b'" in build_command("claude", "a b")


class TestResolve:
    def test_no_config_host_claude_subagent(self) -> None:
        assert resolve("code", "claude", {}) == {"mode": "subagent"}

    def test_no_config_host_agy_inline(self) -> None:
        assert resolve("review", "agy", {}) == {"mode": "inline"}

    def test_no_config_host_codex_subagent(self) -> None:
        assert resolve("review", "codex", {}) == {"mode": "subagent"}

    def test_cli_override_no_config(self) -> None:
        got = resolve("review", "claude", {}, cli="codex")
        assert got["mode"] == "cli"
        assert got["command"] == BASE_COMMANDS["codex"]

    def test_claude_alias_is_subagent_with_model(self) -> None:
        cfg = {"code": RoleConfig("claude", "sonnet")}
        assert resolve("code", "claude", cfg) == {"mode": "subagent", "model": "sonnet"}

    def test_claude_non_alias_model_is_cli(self) -> None:
        cfg = {"code": RoleConfig("claude", "claude-sonnet-5-5")}
        assert resolve("code", "claude", cfg)["mode"] == "cli"

    def test_other_cli_is_cli_mode(self) -> None:
        cfg = {"review": RoleConfig("agy", "gemini-4-argon-medium")}
        got = resolve("review", "claude", cfg)
        assert got["mode"] == "cli"
        assert got["command"].endswith("--model gemini-4-argon-medium")

    @pytest.mark.parametrize("host", ["copilot", "agy"])
    def test_model_on_host_that_cannot_choose_a_subagent_model_is_cli(self, host: str) -> None:
        cli = canonical_cli(host)
        cfg = {"review": RoleConfig(cli, "some-model")}
        assert resolve("review", host, cfg)["mode"] == "cli"

    def test_codex_model_is_subagent_with_model(self) -> None:
        cfg = {"code": RoleConfig("codex", "gpt-5.6-luna")}
        assert resolve("code", "codex", cfg) == {"mode": "subagent", "model": "gpt-5.6-luna"}

    def test_codex_model_and_effort_is_subagent_with_both(self) -> None:
        cfg = {"code": RoleConfig("codex", "gpt-5.6-luna", "low")}
        assert resolve("code", "codex", cfg) == {
            "mode": "subagent",
            "model": "gpt-5.6-luna",
            "effort": "low",
        }

    def test_codex_effort_only_is_subagent_with_effort(self) -> None:
        cfg = {"code": RoleConfig("codex", None, "high")}
        assert resolve("code", "codex", cfg) == {"mode": "subagent", "effort": "high"}

    def test_codex_without_model_or_effort_is_plain_subagent(self) -> None:
        cfg = {"code": RoleConfig("codex")}
        assert resolve("code", "codex", cfg) == {"mode": "subagent"}

    def test_codex_role_on_claude_host_is_cli(self) -> None:
        cfg = {"code": RoleConfig("codex", "gpt-5.6-luna", "low")}
        assert resolve("code", "claude", cfg)["mode"] == "cli"

    def test_cli_override_to_codex_from_codex_host_is_subagent(self) -> None:
        cfg = {"review": RoleConfig("codex", "gpt-5.6-luna", "low")}
        got = resolve("review", "codex", cfg, cli="codex")
        assert got == {"mode": "subagent", "model": "gpt-5.6-luna", "effort": "low"}

    def test_copilot_model_is_cli_and_no_model_is_subagent(self) -> None:
        # Copilot's task tool does not honour a chosen model (its schema allowed only "auto").
        with_model = resolve("code", "copilot", {"code": RoleConfig("copilot", "gpt-6.1-sol")})
        assert with_model["mode"] == "cli"
        assert with_model["command"].endswith("--model gpt-6.1-sol")
        assert resolve("code", "copilot", {"code": RoleConfig("copilot")}) == {"mode": "subagent"}

    def test_override_drops_model_of_other_cli(self) -> None:
        cfg = {"review": RoleConfig("agy", "gemini-4-argon-medium")}
        got = resolve("review", "claude", cfg, cli="codex")
        assert got["command"] == BASE_COMMANDS["codex"]

    def test_override_keeps_model_of_matching_cli(self) -> None:
        cfg = {"review": RoleConfig("agy", "m")}
        got = resolve("review", "claude", cfg, cli="antigravity")
        assert got["command"].endswith("--model m")

    def test_unknown_inputs(self) -> None:
        with pytest.raises(AgentConfigError):
            resolve("nope", "claude", {})
        with pytest.raises(AgentConfigError):
            resolve("code", "nope", {})
        with pytest.raises(AgentConfigError):
            resolve("code", "claude", {}, cli="nope")


def _runner(
    outputs: dict[str, tuple[int, str]], calls: list[list[str]]
) -> Callable[[list[str]], subprocess.CompletedProcess[str]]:
    def run(argv: list[str]) -> subprocess.CompletedProcess[str]:
        calls.append(argv)
        code, out = outputs[argv[0]]
        return subprocess.CompletedProcess(argv, code, out, "boom" if code else "")

    return run


def _which_all(name: str) -> str | None:
    return f"/bin/{name}"


class TestCheckModels:
    def test_known_models_pass_one_call_per_cli(self) -> None:
        calls: list[list[str]] = []
        cfg = {
            "review": RoleConfig("agy", "gemini-4-argon-high"),
            "plan_review": RoleConfig("agy", "gemini-4-argon-medium"),
            "code": RoleConfig("codex", "gpt-6-luna"),
            "adversarial_review": RoleConfig("copilot", "gpt-6.1-sol"),
        }
        runner = _runner(
            {"agy": (0, AGY_LIST), "codex": (0, CODEX_LIST), "copilot": (0, COPILOT_LIST)}, calls
        )
        errors, notes = check_models(cfg, runner, _which_all)
        assert (errors, notes) == ([], [])
        assert sorted(c[0] for c in calls) == ["agy", "codex", "copilot"]

    def test_unknown_and_prefix_only_rejected(self) -> None:
        cfg = {"review": RoleConfig("agy", "gemini-4-argon")}
        errors, _ = check_models(cfg, _runner({"agy": (0, AGY_LIST)}, []), _which_all)
        assert len(errors) == 1 and "gemini-4-argon" in errors[0]

    def test_other_section_values_not_models(self) -> None:
        cfg = {"review": RoleConfig("copilot", "default")}
        errors, _ = check_models(cfg, _runner({"copilot": (0, COPILOT_LIST)}, []), _which_all)
        assert errors

    def test_missing_cli(self) -> None:
        cfg = {"review": RoleConfig("codex", "x")}
        errors, _ = check_models(cfg, _runner({}, []), lambda _n: None)
        assert errors and "not installed" in errors[0]

    def test_lister_failure(self) -> None:
        cfg = {"review": RoleConfig("agy", "x")}
        errors, _ = check_models(cfg, _runner({"agy": (2, "")}, []), _which_all)
        assert errors and "exited 2" in errors[0]

    def test_unparseable_codex_output(self) -> None:
        cfg = {"review": RoleConfig("codex", "x")}
        errors, _ = check_models(cfg, _runner({"codex": (0, "not json")}, []), _which_all)
        assert errors and "cannot parse" in errors[0]

    def test_claude_alias_passes_other_noted(self) -> None:
        cfg = {"code": RoleConfig("claude", "sonnet"), "plan": RoleConfig("claude", "custom")}
        errors, notes = check_models(cfg, _runner({}, []), _which_all)
        assert errors == [] and len(notes) == 1 and "custom" in notes[0]


class TestTaskWiring:
    def _run(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path, **kwargs: object) -> None:
        monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
        monkeypatch.setattr(ac, "REPO_ROOT", tmp_path)
        action = task_agent_cmd()["actions"][0]
        action(**kwargs)

    def test_one_json_line(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        self._run(monkeypatch, tmp_path, role="code", host="claude")
        assert json.loads(capsys.readouterr().out.strip().splitlines()[-1]) == {"mode": "subagent"}

    @pytest.mark.parametrize("kwargs", [{"role": "code"}, {"host": "claude"}, {}])
    def test_missing_args_exit_1(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path, kwargs: dict[str, str]
    ) -> None:
        with pytest.raises(SystemExit) as exc:
            self._run(monkeypatch, tmp_path, **kwargs)
        assert exc.value.code == 1

    def test_bad_role_exit_1(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
        with pytest.raises(SystemExit):
            self._run(monkeypatch, tmp_path, role="x", host="claude")

    def test_check_exits_1_on_errors(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        cfg_dir = tmp_path / "pyproject-template"
        cfg_dir.mkdir()
        (cfg_dir / "agents.toml").write_text('[roles.review]\ncli = "agy"\nmodel = "x"\n')
        monkeypatch.setattr(ac.shutil, "which", lambda _n: None)
        monkeypatch.setattr(ac, "check_models", lambda c: (["bad"], []))
        with pytest.raises(SystemExit) as exc:
            self._run(monkeypatch, tmp_path, check=True)
        assert exc.value.code == 1
        assert json.loads(capsys.readouterr().out.strip().splitlines()[-1])["ok"] is False

    def test_check_ok_without_config(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        self._run(monkeypatch, tmp_path, check=True)
        assert json.loads(capsys.readouterr().out.strip())["ok"] is True
