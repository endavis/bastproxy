"""Tests for doit task autodiscovery."""

from pathlib import Path

import pytest

from tools.doit import discover_tasks


class TestDiscoverTasks:
    """Tests for discover_tasks function."""

    def test_discovers_doit_config(self) -> None:
        """Test that DOIT_CONFIG is discovered."""
        discovered = discover_tasks()
        assert "DOIT_CONFIG" in discovered
        assert isinstance(discovered["DOIT_CONFIG"], dict)

    def test_discovers_task_functions(self) -> None:
        """Test that task_* functions are discovered."""
        discovered = discover_tasks()

        # Check some known tasks exist
        assert "task_build" in discovered
        assert "task_check" in discovered
        assert "task_test" in discovered
        assert "task_lint" in discovered
        assert "task_benchmark" in discovered

    def test_all_discovered_tasks_are_callable(self) -> None:
        """Test that all discovered task_* items are callable."""
        discovered = discover_tasks()

        for name, obj in discovered.items():
            if name.startswith("task_"):
                assert callable(obj), f"{name} should be callable"

    def test_does_not_discover_private_functions(self) -> None:
        """Test that private functions are not discovered."""
        discovered = discover_tasks()

        for name in discovered:
            # Should only have task_* or DOIT_CONFIG
            is_valid = name.startswith("task_") or name == "DOIT_CONFIG"
            assert is_valid, f"Unexpected item discovered: {name}"

    def test_discovered_tasks_return_valid_doit_format(self) -> None:
        """Test that discovered tasks return valid doit task dicts."""
        discovered = discover_tasks()

        # Test a few known tasks return proper dict structure
        task_build = discovered["task_build"]
        result = task_build()

        assert isinstance(result, dict)
        assert "actions" in result or "task_dep" in result


class TestDefaultTasks:
    """DOIT_CONFIG["default_tasks"] must name tasks, not doit commands (#1071)."""

    def test_default_tasks_name_discovered_tasks(self) -> None:
        """Every default task is a task_* function the dodo loader discovers."""
        discovered = discover_tasks()
        default_tasks = discovered["DOIT_CONFIG"]["default_tasks"]

        assert default_tasks
        for name in default_tasks:
            assert f"task_{name}" in discovered, f"{name!r} is not a doit task"

    def test_default_task_lists_tasks_without_reopening_the_database(
        self,
        capsys: pytest.CaptureFixture[str],
        monkeypatch: pytest.MonkeyPatch,
        tmp_path: Path,
    ) -> None:
        """Running the default task opens doit's database once, not twice (#1198).

        Under ``dbm.gnu`` a second open of ``.doit.db`` while the outer run holds it
        fails with EAGAIN, so the listing must reuse the running dependency manager.
        """
        import doit.cmd_base as cmd_base
        from doit.cmd_base import ModuleTaskLoader
        from doit.doit_cmd import DoitMain

        import dodo

        opened: list[str] = []
        real_dependency = cmd_base.Dependency

        class CountingDependency(real_dependency):  # type: ignore[misc, valid-type]
            def __init__(self, *args: object, **kwargs: object) -> None:
                opened.append(str(args[1]))
                super().__init__(*args, **kwargs)

        monkeypatch.setattr(cmd_base, "Dependency", CountingDependency)
        db_file = tmp_path / "doit.db"

        code = DoitMain(ModuleTaskLoader(dodo)).run(["--db-file", str(db_file), "default"])

        assert code == 0
        assert opened == [str(db_file)]
        assert "cleanup" in capsys.readouterr().out
