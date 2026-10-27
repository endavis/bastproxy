"""Tests for benchmark.py doit tasks."""

from tools.doit.benchmark import task_benchmark, task_benchmark_compare, task_benchmark_save


class TestTaskBenchmark:
    """Tests for task_benchmark function."""

    def test_returns_valid_doit_task(self) -> None:
        """Test that task_benchmark returns a valid doit task dict."""
        result = task_benchmark()
        assert isinstance(result, dict)
        assert "actions" in result
        assert "title" in result

    def test_actions_contain_benchmark_flags(self) -> None:
        """Test that actions include benchmark-specific flags."""
        result = task_benchmark()
        action = result["actions"][0]
        assert "--benchmark-enable" in action
        assert "--benchmark-only" in action
        assert "tests/benchmarks/" in action


class TestTaskBenchmarkSave:
    """Tests for task_benchmark_save function."""

    def test_returns_valid_doit_task(self) -> None:
        """Test that task_benchmark_save returns a valid doit task dict."""
        result = task_benchmark_save()
        assert isinstance(result, dict)
        assert "actions" in result
        assert "title" in result

    def test_actions_contain_save_flags(self) -> None:
        """Test that actions include save-specific flags."""
        result = task_benchmark_save()
        action = result["actions"][0]
        assert "--benchmark-enable" in action
        assert "--benchmark-only" in action
        assert "--benchmark-save=baseline" in action
        assert "--benchmark-storage=tmp/benchmarks" in action
        assert "tests/benchmarks/" in action


class TestTaskBenchmarkCompare:
    """Tests for task_benchmark_compare function."""

    def test_returns_valid_doit_task(self) -> None:
        """Test that task_benchmark_compare returns a valid doit task dict."""
        result = task_benchmark_compare()
        assert isinstance(result, dict)
        assert "actions" in result
        assert "title" in result

    def test_actions_contain_compare_flags(self) -> None:
        """Test that actions include compare-specific flags."""
        result = task_benchmark_compare()
        action = result["actions"][0]
        assert "--benchmark-enable" in action
        assert "--benchmark-only" in action
        assert "--benchmark-compare" in action.split()
        assert "--benchmark-storage=tmp/benchmarks" in action
        assert "tests/benchmarks/" in action

    def test_compare_uses_latest_save_not_a_pinned_run(self) -> None:
        """Test that the compare flag names no run, so the latest save is used (#838).

        ``benchmark_save`` numbers every save (0001_baseline, 0002_baseline, ...).
        A pinned run ID keeps comparing against the first save after later ones
        exist.
        """
        action = task_benchmark_compare()["actions"][0]
        assert not [arg for arg in action.split() if arg.startswith("--benchmark-compare=")]
