"""Tests for doit task autodiscovery."""

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
