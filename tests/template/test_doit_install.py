"""Tests for install.py doit tasks."""

from unittest.mock import MagicMock, patch

from tools.doit.install import (
    task_install,
    task_install_dev,
    task_install_gh,
    task_install_jq,
)


class TestTaskInstall:
    """Tests for task_install function."""

    def test_returns_valid_doit_task(self) -> None:
        """Test that task_install returns a valid doit task dict."""
        result = task_install()
        assert isinstance(result, dict)
        assert "actions" in result
        assert "title" in result

    def test_actions_contain_uv_sync(self) -> None:
        """Test that actions include uv sync."""
        result = task_install()
        assert "uv sync" in result["actions"]


class TestTaskInstallDev:
    """Tests for task_install_dev function."""

    def test_returns_valid_doit_task(self) -> None:
        """Test that task_install_dev returns a valid doit task dict."""
        result = task_install_dev()
        assert isinstance(result, dict)
        assert "actions" in result
        assert "title" in result

    def test_actions_contain_uv_sync_all_extras(self) -> None:
        """Test that actions include uv sync with all extras and dev."""
        result = task_install_dev()
        assert "uv sync --all-extras --dev" in result["actions"]

    def test_no_assume_unchanged_action(self) -> None:
        """Test that the assume-unchanged workaround for _version.py is not present.

        Regression for the bug fixed in this PR: ``_version.py`` is gitignored
        and untracked upstream, so ``git update-index --assume-unchanged`` would
        fail (cannot mark an untracked file). The previous workaround dated to
        when the file was incorrectly tracked.
        """
        result = task_install_dev()
        for action in result["actions"]:
            assert "assume-unchanged" not in str(action), (
                f"obsolete assume-unchanged action present: {action!r}"
            )


class TestTaskInstallGh:
    """Tests for task_install_gh function."""

    def test_returns_valid_doit_task(self) -> None:
        """Test that task_install_gh returns a valid doit task dict."""
        result = task_install_gh()
        assert isinstance(result, dict)
        assert "actions" in result
        assert "title" in result
        assert len(result["actions"]) == 1
        assert callable(result["actions"][0])

    @patch("tools.doit.install_tools.install_tool")
    def test_action_calls_install_tool_with_correct_args(self, mock_install: MagicMock) -> None:
        """Test that the task action calls install_tool with gh-specific args."""
        result = task_install_gh()
        result["actions"][0]()

        mock_install.assert_called_once_with(
            name="gh",
            repo="cli/cli",
            asset_patterns={},
            version_cmd=["gh", "--version"],
            post_install_message=None,
            extract_binaries=["gh"],
            url_template="https://github.com/cli/cli/releases/download/v{version}/gh_{version}_{os}_{arch}.tar.gz",
            prefer_brew=False,
            sha256=None,
        )

    @patch("tools.doit.install_tools.install_tool")
    def test_uses_url_template_not_asset_patterns(self, mock_install: MagicMock) -> None:
        """Test that gh uses url_template with empty asset_patterns."""
        result = task_install_gh()
        result["actions"][0]()

        kwargs = mock_install.call_args.kwargs
        assert kwargs["asset_patterns"] == {}
        assert "{version}" in kwargs["url_template"]
        assert "{os}" in kwargs["url_template"]
        assert "{arch}" in kwargs["url_template"]

    @patch("tools.doit.install_tools.install_tool")
    def test_prefer_brew_is_false(self, mock_install: MagicMock) -> None:
        """Test that prefer_brew is False for consistent cross-platform behavior."""
        result = task_install_gh()
        result["actions"][0]()

        assert mock_install.call_args.kwargs["prefer_brew"] is False

    @patch("tools.doit.install_tools.install_tool")
    def test_extract_binaries_contains_gh(self, mock_install: MagicMock) -> None:
        """Test that extract_binaries is set to extract the gh binary."""
        result = task_install_gh()
        result["actions"][0]()

        assert mock_install.call_args.kwargs["extract_binaries"] == ["gh"]


class TestTaskInstallJq:
    """Tests for task_install_jq function."""

    def test_returns_valid_doit_task(self) -> None:
        """Test that task_install_jq returns a valid doit task dict."""
        result = task_install_jq()
        assert isinstance(result, dict)
        assert "actions" in result
        assert "title" in result
        assert len(result["actions"]) == 1
        assert callable(result["actions"][0])

    @patch("tools.doit.install_tools.install_tool")
    def test_action_calls_install_tool_with_correct_args(self, mock_install: MagicMock) -> None:
        """Test that the task action calls install_tool with jq-specific args."""
        result = task_install_jq()
        result["actions"][0]()

        mock_install.assert_called_once_with(
            name="jq",
            repo="jqlang/jq",
            asset_patterns={},
            version_cmd=["jq", "--version"],
            post_install_message=None,
            extract_binaries=None,
            url_template={
                "linux": "https://github.com/jqlang/jq/releases/download/{version}/jq-linux-{arch}",
                "darwin": "https://github.com/jqlang/jq/releases/download/{version}/jq-macos-{arch}",
            },
            prefer_brew=False,
            sha256=None,
        )

    @patch("tools.doit.install_tools.install_tool")
    def test_url_template_is_dict_with_linux_and_darwin_only(self, mock_install: MagicMock) -> None:
        """Test that url_template has only linux and darwin keys with placeholders."""
        result = task_install_jq()
        result["actions"][0]()

        url_template = mock_install.call_args.kwargs["url_template"]
        assert isinstance(url_template, dict)
        assert set(url_template) == {"linux", "darwin"}
        for url in url_template.values():
            assert "{version}" in url
            assert "{arch}" in url
            assert "/v{version}/" not in url

    @patch("tools.doit.install_tools.install_tool")
    def test_prefer_brew_is_false(self, mock_install: MagicMock) -> None:
        """Test that prefer_brew is False for consistent cross-platform behavior."""
        result = task_install_jq()
        result["actions"][0]()

        assert mock_install.call_args.kwargs["prefer_brew"] is False
