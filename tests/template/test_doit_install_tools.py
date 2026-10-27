"""Tests for install_tools.py reusable tool installation framework."""

import hashlib
import json
import shutil
import subprocess  # nosec B404 - needed for CompletedProcess in tests
import sys
import tarfile
import tempfile
import zipfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from tools.doit.install_tools import (
    IntegrityError,
    _get_arch,
    create_install_task,
    download_and_extract_archive,
    download_github_release_binary,
    get_install_dir,
    get_latest_github_release,
    install_tool,
    requires_digest,
    sha256_of,
    verify_download,
)

# SHA-256 of an empty file. The urlretrieve mocks below `touch()` their
# destination, so this is the digest a caller must supply for a download from a
# host outside IMPLICITLY_TRUSTED_HOSTS (ADR-9015 custom URLs).
_EMPTY_SHA256 = "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"


class TestGetLatestGithubRelease:
    """Tests for get_latest_github_release function."""

    @patch("tools.doit.install_tools.urllib.request.urlopen")
    @patch("tools.doit.install_tools.urllib.request.Request")
    def test_returns_version_without_v_prefix(
        self, mock_request_cls: MagicMock, mock_urlopen: MagicMock
    ) -> None:
        """Test that leading 'v' is stripped from tag_name."""
        mock_response = MagicMock()
        mock_response.read.return_value = json.dumps({"tag_name": "v2.34.0"}).encode()
        mock_response.__enter__ = MagicMock(return_value=mock_response)
        mock_response.__exit__ = MagicMock(return_value=False)
        mock_urlopen.return_value = mock_response

        result = get_latest_github_release("direnv/direnv")

        assert result == "2.34.0"

    @patch("tools.doit.install_tools.urllib.request.urlopen")
    @patch("tools.doit.install_tools.urllib.request.Request")
    def test_returns_version_without_v_when_no_prefix(
        self, mock_request_cls: MagicMock, mock_urlopen: MagicMock
    ) -> None:
        """Test version returned as-is when no 'v' prefix."""
        mock_response = MagicMock()
        mock_response.read.return_value = json.dumps({"tag_name": "2.34.0"}).encode()
        mock_response.__enter__ = MagicMock(return_value=mock_response)
        mock_response.__exit__ = MagicMock(return_value=False)
        mock_urlopen.return_value = mock_response

        result = get_latest_github_release("owner/repo")

        assert result == "2.34.0"

    @patch.dict("os.environ", {"GITHUB_TOKEN": "test-token"})
    @patch("tools.doit.install_tools.urllib.request.urlopen")
    @patch("tools.doit.install_tools.urllib.request.Request")
    def test_adds_auth_header_when_token_present(
        self, mock_request_cls: MagicMock, mock_urlopen: MagicMock
    ) -> None:
        """Test that GITHUB_TOKEN is used for Authorization header."""
        mock_request_instance = MagicMock()
        mock_request_cls.return_value = mock_request_instance

        mock_response = MagicMock()
        mock_response.read.return_value = json.dumps({"tag_name": "v1.0.0"}).encode()
        mock_response.__enter__ = MagicMock(return_value=mock_response)
        mock_response.__exit__ = MagicMock(return_value=False)
        mock_urlopen.return_value = mock_response

        get_latest_github_release("owner/repo")

        mock_request_instance.add_header.assert_called_once_with(
            "Authorization", "token test-token"
        )

    @patch("tools.doit.install_tools.urllib.request.urlopen")
    @patch("tools.doit.install_tools.urllib.request.Request")
    def test_no_auth_header_when_no_token(
        self,
        mock_request_cls: MagicMock,
        mock_urlopen: MagicMock,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Test that no Authorization header is added without GITHUB_TOKEN."""
        monkeypatch.delenv("GITHUB_TOKEN", raising=False)
        mock_request_instance = MagicMock()
        mock_request_cls.return_value = mock_request_instance

        mock_response = MagicMock()
        mock_response.read.return_value = json.dumps({"tag_name": "v1.0.0"}).encode()
        mock_response.__enter__ = MagicMock(return_value=mock_response)
        mock_response.__exit__ = MagicMock(return_value=False)
        mock_urlopen.return_value = mock_response

        get_latest_github_release("owner/repo")

        mock_request_instance.add_header.assert_not_called()

    @patch("tools.doit.install_tools.urllib.request.urlopen")
    @patch("tools.doit.install_tools.urllib.request.Request")
    def test_constructs_correct_api_url(
        self, mock_request_cls: MagicMock, mock_urlopen: MagicMock
    ) -> None:
        """Test that the correct GitHub API URL is constructed."""
        mock_response = MagicMock()
        mock_response.read.return_value = json.dumps({"tag_name": "v1.0.0"}).encode()
        mock_response.__enter__ = MagicMock(return_value=mock_response)
        mock_response.__exit__ = MagicMock(return_value=False)
        mock_urlopen.return_value = mock_response

        get_latest_github_release("owner/repo")

        mock_request_cls.assert_called_once_with(
            "https://api.github.com/repos/owner/repo/releases/latest"
        )


class TestGetInstallDir:
    """Tests for get_install_dir function."""

    @patch("tools.doit.install_tools.Path.home")
    def test_returns_local_bin_path(self, mock_home: MagicMock, tmp_path: Path) -> None:
        """Test that ~/.local/bin path is returned."""
        mock_home.return_value = tmp_path
        result = get_install_dir()
        assert result == tmp_path / ".local" / "bin"

    @patch("tools.doit.install_tools.Path.home")
    def test_creates_directory_if_not_exists(self, mock_home: MagicMock, tmp_path: Path) -> None:
        """Test that the directory is created when it does not exist."""
        mock_home.return_value = tmp_path
        expected = tmp_path / ".local" / "bin"
        assert not expected.exists()

        get_install_dir()

        assert expected.exists()

    @patch("tools.doit.install_tools.Path.home")
    def test_no_error_if_directory_exists(self, mock_home: MagicMock, tmp_path: Path) -> None:
        """Test that no error occurs when directory already exists."""
        mock_home.return_value = tmp_path
        expected = tmp_path / ".local" / "bin"
        expected.mkdir(parents=True)

        result = get_install_dir()

        assert result == expected


class TestDownloadGithubReleaseBinary:
    """Tests for download_github_release_binary function."""

    @patch("tools.doit.install_tools.get_install_dir")
    @patch("tools.doit.install_tools.urllib.request.urlretrieve")
    def test_downloads_to_correct_path(
        self,
        mock_urlretrieve: MagicMock,
        mock_get_install_dir: MagicMock,
        tmp_path: Path,
    ) -> None:
        """Test that binary is downloaded to the correct destination."""
        mock_get_install_dir.return_value = tmp_path
        dest = tmp_path / "mytool"
        dest.touch()

        result = download_github_release_binary(
            repo="owner/repo",
            version="1.2.3",
            asset_pattern="mytool.linux-amd64",
            dest_name="mytool",
        )

        assert result == dest
        mock_urlretrieve.assert_called_once_with(
            "https://github.com/owner/repo/releases/download/v1.2.3/mytool.linux-amd64",
            dest,
        )

    @patch("tools.doit.install_tools.get_install_dir")
    @patch("tools.doit.install_tools.urllib.request.urlretrieve")
    def test_version_placeholder_in_asset_pattern(
        self,
        mock_urlretrieve: MagicMock,
        mock_get_install_dir: MagicMock,
        tmp_path: Path,
    ) -> None:
        """Test that {version} placeholder is substituted in asset_pattern."""
        mock_get_install_dir.return_value = tmp_path
        dest = tmp_path / "tool"
        dest.touch()

        download_github_release_binary(
            repo="owner/repo",
            version="3.0.0",
            asset_pattern="tool-v{version}-linux-amd64",
            dest_name="tool",
        )

        mock_urlretrieve.assert_called_once_with(
            "https://github.com/owner/repo/releases/download/v3.0.0/tool-v3.0.0-linux-amd64",
            dest,
        )

    @pytest.mark.skipif(
        sys.platform == "win32", reason="Windows does not support Unix file permissions"
    )
    @patch("tools.doit.install_tools.get_install_dir")
    @patch("tools.doit.install_tools.urllib.request.urlretrieve")
    def test_sets_executable_permissions(
        self,
        mock_urlretrieve: MagicMock,
        mock_get_install_dir: MagicMock,
        tmp_path: Path,
    ) -> None:
        """Test that the binary is made executable after download."""
        mock_get_install_dir.return_value = tmp_path
        dest = tmp_path / "mytool"
        dest.touch(mode=0o644)

        download_github_release_binary(
            repo="owner/repo",
            version="1.0.0",
            asset_pattern="mytool.linux-amd64",
            dest_name="mytool",
        )

        assert dest.stat().st_mode & 0o755 == 0o755


class TestInstallTool:
    """Tests for install_tool function."""

    @patch("tools.doit.install_tools.subprocess.run")
    @patch("tools.doit.install_tools.shutil.which", return_value="/usr/bin/mytool")
    def test_skips_install_when_tool_exists(
        self, mock_which: MagicMock, mock_run: MagicMock, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """Test that install is skipped when tool is already on PATH."""
        mock_run.return_value = subprocess.CompletedProcess(
            args=["mytool", "--version"], returncode=0, stdout="1.0.0\n", stderr=""
        )

        install_tool(
            name="mytool",
            repo="owner/repo",
            asset_patterns={"linux": "mytool.linux-amd64"},
        )

        captured = capsys.readouterr()
        assert "already installed" in captured.out
        assert "1.0.0" in captured.out

    @patch("tools.doit.install_tools.subprocess.run")
    @patch("tools.doit.install_tools.shutil.which", return_value="/usr/bin/mytool")
    def test_uses_custom_version_cmd(self, mock_which: MagicMock, mock_run: MagicMock) -> None:
        """Test that custom version_cmd is used for version check."""
        mock_run.return_value = subprocess.CompletedProcess(
            args=["mytool", "version"], returncode=0, stdout="2.0.0\n", stderr=""
        )

        install_tool(
            name="mytool",
            repo="owner/repo",
            asset_patterns={"linux": "mytool.linux-amd64"},
            version_cmd=["mytool", "version"],
        )

        mock_run.assert_called_once_with(
            ["mytool", "version"],
            capture_output=True,
            text=True,
            check=True,
        )

    @patch("tools.doit.install_tools.subprocess.run")
    @patch("tools.doit.install_tools.shutil.which", return_value="/usr/bin/mytool")
    def test_falls_back_to_stderr_for_version(
        self, mock_which: MagicMock, mock_run: MagicMock, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """Test that stderr is used when stdout is empty for version output."""
        mock_run.return_value = subprocess.CompletedProcess(
            args=["mytool", "--version"], returncode=0, stdout="", stderr="3.0.0\n"
        )

        install_tool(
            name="mytool",
            repo="owner/repo",
            asset_patterns={"linux": "mytool.linux-amd64"},
        )

        captured = capsys.readouterr()
        assert "3.0.0" in captured.out

    @patch("tools.doit.install_tools.download_github_release_binary")
    @patch("tools.doit.install_tools.get_latest_github_release", return_value="2.0.0")
    @patch("tools.doit.install_tools.platform.system", return_value="Linux")
    @patch("tools.doit.install_tools.shutil.which", return_value=None)
    def test_installs_on_linux(
        self,
        mock_which: MagicMock,
        mock_system: MagicMock,
        mock_get_release: MagicMock,
        mock_download: MagicMock,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """Test that tool is downloaded on Linux when not installed."""
        install_tool(
            name="mytool",
            repo="owner/repo",
            asset_patterns={"linux": "mytool.linux-amd64"},
        )

        mock_download.assert_called_once_with(
            repo="owner/repo",
            version="2.0.0",
            asset_pattern="mytool.linux-amd64",
            dest_name="mytool",
            sha256=None,
        )
        captured = capsys.readouterr()
        assert "mytool installed" in captured.out

    @patch("tools.doit.install_tools.subprocess.run")
    @patch("tools.doit.install_tools.get_latest_github_release", return_value="2.0.0")
    @patch("tools.doit.install_tools.platform.system", return_value="Darwin")
    @patch("tools.doit.install_tools.shutil.which", return_value=None)
    def test_installs_via_brew_on_darwin(
        self,
        mock_which: MagicMock,
        mock_system: MagicMock,
        mock_get_release: MagicMock,
        mock_run: MagicMock,
    ) -> None:
        """Test that brew is used on macOS."""
        install_tool(
            name="mytool",
            repo="owner/repo",
            asset_patterns={"linux": "mytool.linux-amd64"},
        )

        mock_run.assert_called_once_with(["brew", "install", "mytool"], check=True)

    @patch("tools.doit.install_tools.get_latest_github_release", return_value="1.0.0")
    @patch("tools.doit.install_tools.platform.system", return_value="Windows")
    @patch("tools.doit.install_tools.shutil.which", return_value=None)
    def test_exits_on_unsupported_os(
        self,
        mock_which: MagicMock,
        mock_system: MagicMock,
        mock_get_release: MagicMock,
    ) -> None:
        """Test that sys.exit is called for unsupported OS."""
        with pytest.raises(SystemExit):
            install_tool(
                name="mytool",
                repo="owner/repo",
                asset_patterns={"linux": "mytool.linux-amd64"},
            )

    @patch("tools.doit.install_tools.download_github_release_binary")
    @patch("tools.doit.install_tools.get_latest_github_release", return_value="1.0.0")
    @patch("tools.doit.install_tools.platform.system", return_value="Linux")
    @patch("tools.doit.install_tools.shutil.which", return_value=None)
    def test_prints_post_install_message(
        self,
        mock_which: MagicMock,
        mock_system: MagicMock,
        mock_get_release: MagicMock,
        mock_download: MagicMock,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """Test that post_install_message is printed after install."""
        install_tool(
            name="mytool",
            repo="owner/repo",
            asset_patterns={"linux": "mytool.linux-amd64"},
            post_install_message="Run 'mytool init' to get started.",
        )

        captured = capsys.readouterr()
        assert "Run 'mytool init' to get started." in captured.out

    @patch("tools.doit.install_tools.download_github_release_binary")
    @patch("tools.doit.install_tools.get_latest_github_release", return_value="1.0.0")
    @patch("tools.doit.install_tools.platform.system", return_value="Linux")
    @patch("tools.doit.install_tools.shutil.which", return_value=None)
    def test_no_post_install_message_when_none(
        self,
        mock_which: MagicMock,
        mock_system: MagicMock,
        mock_get_release: MagicMock,
        mock_download: MagicMock,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """Test that no extra message is printed when post_install_message is None."""
        install_tool(
            name="mytool",
            repo="owner/repo",
            asset_patterns={"linux": "mytool.linux-amd64"},
        )

        captured = capsys.readouterr()
        assert captured.out.strip().endswith("mytool installed.")

    @patch("tools.doit.install_tools.subprocess.run")
    @patch("tools.doit.install_tools.shutil.which", return_value="/usr/bin/mytool")
    def test_default_version_cmd(self, mock_which: MagicMock, mock_run: MagicMock) -> None:
        """Test that default version_cmd is [name, '--version']."""
        mock_run.return_value = subprocess.CompletedProcess(
            args=["mytool", "--version"], returncode=0, stdout="1.0.0\n", stderr=""
        )

        install_tool(
            name="mytool",
            repo="owner/repo",
            asset_patterns={"linux": "mytool.linux-amd64"},
        )

        mock_run.assert_called_once_with(
            ["mytool", "--version"],
            capture_output=True,
            text=True,
            check=True,
        )

    @patch("tools.doit.install_tools.subprocess.run")
    @patch("tools.doit.install_tools.shutil.which", return_value="/usr/bin/mytool")
    def test_already_installed_output_is_cp1252_encodable(
        self, mock_which: MagicMock, mock_run: MagicMock, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """Regression test for #328: already-installed output must encode in cp1252 (Windows)."""
        mock_run.return_value = subprocess.CompletedProcess(
            args=["mytool", "--version"], returncode=0, stdout="1.0.0\n", stderr=""
        )

        install_tool(
            name="mytool",
            repo="owner/repo",
            asset_patterns={"linux": "mytool.linux-amd64"},
        )

        captured = capsys.readouterr()
        # Must not raise UnicodeEncodeError on Windows cp1252 console
        captured.out.encode("cp1252")
        assert "already installed" in captured.out

    @patch("tools.doit.install_tools.download_github_release_binary")
    @patch("tools.doit.install_tools.get_latest_github_release", return_value="2.0.0")
    @patch("tools.doit.install_tools.platform.system", return_value="Linux")
    @patch("tools.doit.install_tools.shutil.which", return_value=None)
    def test_fresh_install_output_is_cp1252_encodable(
        self,
        mock_which: MagicMock,
        mock_system: MagicMock,
        mock_get_release: MagicMock,
        mock_download: MagicMock,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """Regression test for #328: fresh-install output must encode in cp1252 (Windows)."""
        install_tool(
            name="mytool",
            repo="owner/repo",
            asset_patterns={"linux": "mytool.linux-amd64"},
        )

        captured = capsys.readouterr()
        # Must not raise UnicodeEncodeError on Windows cp1252 console
        captured.out.encode("cp1252")
        assert "mytool installed" in captured.out

    @patch("tools.doit.install_tools.urllib.request.urlretrieve")
    @patch("tools.doit.install_tools.get_install_dir")
    @patch("tools.doit.install_tools._get_arch", return_value="amd64")
    @patch("tools.doit.install_tools.get_latest_github_release", return_value="1.5.0")
    @patch("tools.doit.install_tools.platform.system", return_value="Linux")
    @patch("tools.doit.install_tools.shutil.which", return_value=None)
    def test_install_with_url_template_substitutes_placeholders(
        self,
        mock_which: MagicMock,
        mock_system: MagicMock,
        mock_get_release: MagicMock,
        mock_arch: MagicMock,
        mock_get_install_dir: MagicMock,
        mock_urlretrieve: MagicMock,
        tmp_path: Path,
    ) -> None:
        """Test that url_template placeholders are substituted."""
        mock_get_install_dir.return_value = tmp_path
        mock_urlretrieve.side_effect = lambda url, dest: Path(dest).touch()

        install_tool(
            name="terraform",
            repo="hashicorp/terraform",
            asset_patterns={},
            url_template="https://releases.example.com/{version}/terraform_{os}_{arch}",
            sha256=_EMPTY_SHA256,
        )

        called_url = mock_urlretrieve.call_args.args[0]
        assert called_url == "https://releases.example.com/1.5.0/terraform_linux_amd64"

    @patch("tools.doit.install_tools.download_and_extract_archive")
    @patch("tools.doit.install_tools.get_install_dir")
    @patch("tools.doit.install_tools.get_latest_github_release", return_value="1.0.0")
    @patch("tools.doit.install_tools.platform.system", return_value="Linux")
    @patch("tools.doit.install_tools.shutil.which", return_value=None)
    def test_install_with_extract_binaries_calls_extract(
        self,
        mock_which: MagicMock,
        mock_system: MagicMock,
        mock_get_release: MagicMock,
        mock_get_install_dir: MagicMock,
        mock_extract: MagicMock,
        tmp_path: Path,
    ) -> None:
        """Test that extract_binaries triggers download_and_extract_archive."""
        mock_get_install_dir.return_value = tmp_path

        install_tool(
            name="age",
            repo="FiloSottile/age",
            asset_patterns={"linux": "age-v{version}-linux-amd64.tar.gz"},
            extract_binaries=["age", "age-keygen"],
        )

        mock_extract.assert_called_once()
        args = mock_extract.call_args.args
        assert args[1] == ["age", "age-keygen"]
        assert args[2] == tmp_path

    @patch("tools.doit.install_tools.download_and_extract_archive")
    @patch("tools.doit.install_tools.get_install_dir")
    @patch("tools.doit.install_tools.get_latest_github_release", return_value="1.0.0")
    @patch("tools.doit.install_tools.platform.system", return_value="Linux")
    @patch("tools.doit.install_tools.shutil.which", return_value=None)
    def test_install_with_extract_binaries_dict_resolves_for_linux(
        self,
        mock_which: MagicMock,
        mock_system: MagicMock,
        mock_get_release: MagicMock,
        mock_get_install_dir: MagicMock,
        mock_extract: MagicMock,
        tmp_path: Path,
    ) -> None:
        """Test that a per-platform extract_binaries dict resolves to the linux list."""
        mock_get_install_dir.return_value = tmp_path

        install_tool(
            name="age",
            repo="FiloSottile/age",
            asset_patterns={
                "linux": "age-v{version}-linux-amd64.tar.gz",
                "windows": "age-v{version}-windows-amd64.zip",
            },
            extract_binaries={
                "linux": ["age", "age-keygen"],
                "windows": ["age.exe", "age-keygen.exe"],
            },
        )

        mock_extract.assert_called_once()
        args = mock_extract.call_args.args
        assert args[1] == ["age", "age-keygen"]
        assert args[2] == tmp_path

    @patch("tools.doit.install_tools.download_and_extract_archive")
    @patch("tools.doit.install_tools.get_install_dir")
    @patch("tools.doit.install_tools.get_latest_github_release", return_value="1.0.0")
    @patch("tools.doit.install_tools.platform.system", return_value="Windows")
    @patch("tools.doit.install_tools.shutil.which", return_value=None)
    def test_install_with_extract_binaries_dict_resolves_for_windows(
        self,
        mock_which: MagicMock,
        mock_system: MagicMock,
        mock_get_release: MagicMock,
        mock_get_install_dir: MagicMock,
        mock_extract: MagicMock,
        tmp_path: Path,
    ) -> None:
        """Test that a per-platform extract_binaries dict resolves to the windows list."""
        mock_get_install_dir.return_value = tmp_path

        install_tool(
            name="age",
            repo="FiloSottile/age",
            asset_patterns={
                "linux": "age-v{version}-linux-amd64.tar.gz",
                "windows": "age-v{version}-windows-amd64.zip",
            },
            extract_binaries={
                "linux": ["age", "age-keygen"],
                "windows": ["age.exe", "age-keygen.exe"],
            },
        )

        mock_extract.assert_called_once()
        args = mock_extract.call_args.args
        assert args[1] == ["age.exe", "age-keygen.exe"]
        assert args[2] == tmp_path

    @patch("tools.doit.install_tools.get_latest_github_release", return_value="1.0.0")
    @patch("tools.doit.install_tools.platform.system", return_value="Windows")
    @patch("tools.doit.install_tools.shutil.which", return_value=None)
    def test_install_with_extract_binaries_dict_missing_platform_exits(
        self,
        mock_which: MagicMock,
        mock_system: MagicMock,
        mock_get_release: MagicMock,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """Test that a per-platform extract_binaries dict missing the current OS exits."""
        with pytest.raises(SystemExit):
            install_tool(
                name="age",
                repo="FiloSottile/age",
                asset_patterns={
                    "linux": "age-v{version}-linux-amd64.tar.gz",
                    "windows": "age-v{version}-windows-amd64.zip",
                },
                extract_binaries={"linux": ["age", "age-keygen"]},
            )

        captured = capsys.readouterr()
        assert "Unsupported OS for age: windows" in captured.out

    @patch("tools.doit.install_tools.download_github_release_binary")
    @patch("tools.doit.install_tools.subprocess.run")
    @patch("tools.doit.install_tools.get_latest_github_release", return_value="1.0.0")
    @patch("tools.doit.install_tools.platform.system", return_value="Darwin")
    @patch("tools.doit.install_tools.shutil.which", return_value=None)
    def test_install_with_prefer_brew_false_on_darwin_bypasses_brew(
        self,
        mock_which: MagicMock,
        mock_system: MagicMock,
        mock_get_release: MagicMock,
        mock_run: MagicMock,
        mock_download: MagicMock,
    ) -> None:
        """Test that prefer_brew=False on darwin downloads instead of brew."""
        install_tool(
            name="mytool",
            repo="owner/repo",
            asset_patterns={"darwin": "mytool.darwin-amd64"},
            prefer_brew=False,
        )

        mock_run.assert_not_called()
        mock_download.assert_called_once_with(
            repo="owner/repo",
            version="1.0.0",
            asset_pattern="mytool.darwin-amd64",
            dest_name="mytool",
            sha256=None,
        )

    @patch("tools.doit.install_tools.urllib.request.urlretrieve")
    @patch("tools.doit.install_tools.get_install_dir")
    @patch("tools.doit.install_tools._get_arch", return_value="amd64")
    @patch("tools.doit.install_tools.subprocess.run")
    @patch("tools.doit.install_tools.get_latest_github_release", return_value="1.0.0")
    @patch("tools.doit.install_tools.platform.system", return_value="Darwin")
    @patch("tools.doit.install_tools.shutil.which", return_value=None)
    def test_install_with_url_template_on_darwin_bypasses_brew(
        self,
        mock_which: MagicMock,
        mock_system: MagicMock,
        mock_get_release: MagicMock,
        mock_run: MagicMock,
        mock_arch: MagicMock,
        mock_get_install_dir: MagicMock,
        mock_urlretrieve: MagicMock,
        tmp_path: Path,
    ) -> None:
        """Test that url_template on darwin always bypasses brew."""
        mock_get_install_dir.return_value = tmp_path
        mock_urlretrieve.side_effect = lambda url, dest: Path(dest).touch()

        install_tool(
            name="terraform",
            repo="hashicorp/terraform",
            asset_patterns={},
            url_template="https://releases.example.com/{version}/{os}_{arch}",
            sha256=_EMPTY_SHA256,
        )

        mock_run.assert_not_called()
        mock_urlretrieve.assert_called_once()

    @patch("tools.doit.install_tools.urllib.request.urlretrieve")
    @patch("tools.doit.install_tools.get_install_dir")
    @patch("tools.doit.install_tools._get_arch", return_value="amd64")
    @patch("tools.doit.install_tools.get_latest_github_release", return_value="jq-1.8.2")
    @patch("tools.doit.install_tools.platform.system", return_value="Linux")
    @patch("tools.doit.install_tools.shutil.which", return_value=None)
    def test_install_with_per_os_url_template_resolves_linux(
        self,
        mock_which: MagicMock,
        mock_system: MagicMock,
        mock_get_release: MagicMock,
        mock_arch: MagicMock,
        mock_get_install_dir: MagicMock,
        mock_urlretrieve: MagicMock,
        tmp_path: Path,
    ) -> None:
        """Test that a per-OS url_template dict resolves to the linux entry."""
        mock_get_install_dir.return_value = tmp_path
        mock_urlretrieve.side_effect = lambda url, dest: Path(dest).touch()

        install_tool(
            name="jq",
            repo="jqlang/jq",
            asset_patterns={},
            url_template={
                "linux": "https://github.com/jqlang/jq/releases/download/{version}/jq-linux-{arch}",
                "darwin": "https://github.com/jqlang/jq/releases/download/{version}/jq-macos-{arch}",
            },
        )

        called_url = mock_urlretrieve.call_args.args[0]
        assert called_url == (
            "https://github.com/jqlang/jq/releases/download/jq-1.8.2/jq-linux-amd64"
        )

    @patch("tools.doit.install_tools.urllib.request.urlretrieve")
    @patch("tools.doit.install_tools.get_install_dir")
    @patch("tools.doit.install_tools._get_arch", return_value="arm64")
    @patch("tools.doit.install_tools.subprocess.run")
    @patch("tools.doit.install_tools.get_latest_github_release", return_value="jq-1.8.2")
    @patch("tools.doit.install_tools.platform.system", return_value="Darwin")
    @patch("tools.doit.install_tools.shutil.which", return_value=None)
    def test_install_with_per_os_url_template_resolves_darwin_and_skips_brew(
        self,
        mock_which: MagicMock,
        mock_system: MagicMock,
        mock_get_release: MagicMock,
        mock_run: MagicMock,
        mock_arch: MagicMock,
        mock_get_install_dir: MagicMock,
        mock_urlretrieve: MagicMock,
        tmp_path: Path,
    ) -> None:
        """Test that a per-OS url_template dict resolves to the darwin entry and bypasses brew."""
        mock_get_install_dir.return_value = tmp_path
        mock_urlretrieve.side_effect = lambda url, dest: Path(dest).touch()

        install_tool(
            name="jq",
            repo="jqlang/jq",
            asset_patterns={},
            url_template={
                "linux": "https://github.com/jqlang/jq/releases/download/{version}/jq-linux-{arch}",
                "darwin": "https://github.com/jqlang/jq/releases/download/{version}/jq-macos-{arch}",
            },
        )

        mock_run.assert_not_called()
        called_url = mock_urlretrieve.call_args.args[0]
        assert called_url == (
            "https://github.com/jqlang/jq/releases/download/jq-1.8.2/jq-macos-arm64"
        )

    @patch("tools.doit.install_tools.get_latest_github_release", return_value="1.0.0")
    @patch("tools.doit.install_tools.platform.system", return_value="Windows")
    @patch("tools.doit.install_tools.shutil.which", return_value=None)
    def test_install_with_per_os_url_template_missing_platform_exits(
        self,
        mock_which: MagicMock,
        mock_system: MagicMock,
        mock_get_release: MagicMock,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """Test that a per-OS url_template dict missing the current OS exits without downloading."""
        with pytest.raises(SystemExit):
            install_tool(
                name="jq",
                repo="jqlang/jq",
                asset_patterns={},
                url_template={
                    "linux": "https://example.com/{version}/jq-linux-{arch}",
                    "darwin": "https://example.com/{version}/jq-macos-{arch}",
                },
            )

        captured = capsys.readouterr()
        assert "Unsupported OS for jq: windows" in captured.out

    @patch("tools.doit.install_tools.urllib.request.urlretrieve")
    @patch("tools.doit.install_tools.get_install_dir")
    @patch("tools.doit.install_tools._get_arch", return_value="amd64")
    @patch("tools.doit.install_tools.get_latest_github_release", return_value="1.0.0")
    @patch("tools.doit.install_tools.platform.system", return_value="Linux")
    @patch("tools.doit.install_tools.shutil.which", return_value=None)
    def test_install_with_plain_string_url_template_unchanged(
        self,
        mock_which: MagicMock,
        mock_system: MagicMock,
        mock_get_release: MagicMock,
        mock_arch: MagicMock,
        mock_get_install_dir: MagicMock,
        mock_urlretrieve: MagicMock,
        tmp_path: Path,
    ) -> None:
        """A plain string url_template must not be mistaken for a dict and must behave as before."""
        mock_get_install_dir.return_value = tmp_path
        mock_urlretrieve.side_effect = lambda url, dest: Path(dest).touch()

        install_tool(
            name="mytool",
            repo="owner/repo",
            asset_patterns={},
            url_template="https://releases.example.com/{version}/mytool_{os}_{arch}",
            sha256=_EMPTY_SHA256,
        )

        called_url = mock_urlretrieve.call_args.args[0]
        assert called_url == "https://releases.example.com/1.0.0/mytool_linux_amd64"


class TestCreateInstallTask:
    """Tests for create_install_task function."""

    def test_returns_valid_doit_task(self) -> None:
        """Test that a valid doit task dict is returned."""
        result = create_install_task(
            name="mytool",
            repo="owner/repo",
            asset_patterns={"linux": "mytool.linux-amd64"},
        )

        assert isinstance(result, dict)
        assert "actions" in result
        assert "title" in result
        assert len(result["actions"]) == 1
        assert callable(result["actions"][0])

    @patch("tools.doit.install_tools.install_tool")
    def test_action_calls_install_tool(self, mock_install: MagicMock) -> None:
        """Test that the task action calls install_tool with correct args."""
        result = create_install_task(
            name="mytool",
            repo="owner/repo",
            asset_patterns={"linux": "mytool.linux-amd64"},
            version_cmd=["mytool", "version"],
            post_install_message="Done!",
        )

        # Execute the action
        result["actions"][0]()

        mock_install.assert_called_once_with(
            name="mytool",
            repo="owner/repo",
            asset_patterns={"linux": "mytool.linux-amd64"},
            version_cmd=["mytool", "version"],
            post_install_message="Done!",
            extract_binaries=None,
            url_template=None,
            prefer_brew=True,
            sha256=None,
        )

    @patch("tools.doit.install_tools.install_tool")
    def test_action_passes_none_defaults(self, mock_install: MagicMock) -> None:
        """Test that None defaults are passed through to install_tool."""
        result = create_install_task(
            name="mytool",
            repo="owner/repo",
            asset_patterns={"linux": "mytool.linux-amd64"},
        )

        result["actions"][0]()

        mock_install.assert_called_once_with(
            name="mytool",
            repo="owner/repo",
            asset_patterns={"linux": "mytool.linux-amd64"},
            version_cmd=None,
            post_install_message=None,
            extract_binaries=None,
            url_template=None,
            prefer_brew=True,
            sha256=None,
        )

    @patch("tools.doit.install_tools.install_tool")
    def test_forwards_extract_binaries(self, mock_install: MagicMock) -> None:
        """Test that extract_binaries kwarg is forwarded to install_tool."""
        result = create_install_task(
            name="age",
            repo="FiloSottile/age",
            asset_patterns={"linux": "age.tar.gz"},
            extract_binaries=["age", "age-keygen"],
        )

        result["actions"][0]()

        assert mock_install.call_args.kwargs["extract_binaries"] == ["age", "age-keygen"]

    @patch("tools.doit.install_tools.install_tool")
    def test_forwards_dict_extract_binaries(self, mock_install: MagicMock) -> None:
        """Test that a per-platform extract_binaries dict is forwarded unchanged."""
        per_platform = {
            "linux": ["age", "age-keygen"],
            "windows": ["age.exe", "age-keygen.exe"],
        }
        result = create_install_task(
            name="age",
            repo="FiloSottile/age",
            asset_patterns={
                "linux": "age.tar.gz",
                "windows": "age.zip",
            },
            extract_binaries=per_platform,
        )

        result["actions"][0]()

        assert mock_install.call_args.kwargs["extract_binaries"] == per_platform

    @patch("tools.doit.install_tools.install_tool")
    def test_forwards_url_template(self, mock_install: MagicMock) -> None:
        """Test that url_template kwarg is forwarded to install_tool."""
        template = "https://github.com/o/r/releases/download/v1/{version}/{os}/{arch}/tool.zip"
        result = create_install_task(
            name="terraform",
            repo="hashicorp/terraform",
            asset_patterns={},
            url_template=template,
        )

        result["actions"][0]()

        assert mock_install.call_args.kwargs["url_template"] == template

    @patch("tools.doit.install_tools.install_tool")
    def test_forwards_dict_url_template(self, mock_install: MagicMock) -> None:
        """Test that a per-OS url_template dict is forwarded unchanged."""
        template = {
            "linux": "https://github.com/jqlang/jq/releases/download/{version}/jq-linux-{arch}",
            "darwin": "https://github.com/jqlang/jq/releases/download/{version}/jq-macos-{arch}",
        }
        result = create_install_task(
            name="jq",
            repo="jqlang/jq",
            asset_patterns={},
            url_template=template,
        )

        result["actions"][0]()

        assert mock_install.call_args.kwargs["url_template"] == template

    @patch("tools.doit.install_tools.install_tool")
    def test_forwards_prefer_brew(self, mock_install: MagicMock) -> None:
        """Test that prefer_brew kwarg is forwarded to install_tool."""
        result = create_install_task(
            name="mytool",
            repo="owner/repo",
            asset_patterns={"linux": "mytool"},
            prefer_brew=False,
        )

        result["actions"][0]()

        assert mock_install.call_args.kwargs["prefer_brew"] is False


class TestGetArch:
    """Tests for _get_arch internal helper."""

    @patch("tools.doit.install_tools.platform.machine", return_value="x86_64")
    def test_x86_64_maps_to_amd64(self, mock_machine: MagicMock) -> None:
        assert _get_arch() == "amd64"

    @patch("tools.doit.install_tools.platform.machine", return_value="aarch64")
    def test_aarch64_maps_to_arm64(self, mock_machine: MagicMock) -> None:
        assert _get_arch() == "arm64"

    @patch("tools.doit.install_tools.platform.machine", return_value="arm64")
    def test_arm64_passthrough(self, mock_machine: MagicMock) -> None:
        assert _get_arch() == "arm64"

    @patch("tools.doit.install_tools.platform.machine", return_value="riscv64")
    def test_unknown_passthrough(self, mock_machine: MagicMock) -> None:
        assert _get_arch() == "riscv64"


def _make_targz(path: Path, files: dict[str, bytes]) -> None:
    """Build a .tar.gz with the given filename->content map."""
    with tarfile.open(path, "w:gz") as tar:
        for name, content in files.items():
            info = tarfile.TarInfo(name=name)
            info.size = len(content)
            info.mode = 0o644
            import io

            tar.addfile(info, io.BytesIO(content))


def _make_zip(path: Path, files: dict[str, bytes]) -> None:
    """Build a .zip with the given filename->content map."""
    with zipfile.ZipFile(path, "w") as zf:
        for name, content in files.items():
            zf.writestr(name, content)


class TestDownloadAndExtractArchive:
    """Tests for download_and_extract_archive function."""

    def test_extracts_targz_with_multiple_binaries(self, tmp_path: Path) -> None:
        fixture = tmp_path / "fixture.tar.gz"
        _make_targz(
            fixture,
            {"age/age": b"age-binary", "age/age-keygen": b"age-keygen-binary"},
        )
        dest = tmp_path / "out"

        with patch(
            "tools.doit.install_tools.urllib.request.urlretrieve",
            side_effect=lambda url, d: shutil.copy(fixture, d),
        ):
            result = download_and_extract_archive(
                "https://github.com/o/r/releases/download/v1/age.tar.gz",
                ["age", "age-keygen"],
                dest,
            )

        assert (dest / "age").read_bytes() == b"age-binary"
        assert (dest / "age-keygen").read_bytes() == b"age-keygen-binary"
        assert result == [dest / "age", dest / "age-keygen"]

    def test_extracts_zip_with_single_binary(self, tmp_path: Path) -> None:
        fixture = tmp_path / "fixture.zip"
        _make_zip(fixture, {"terraform": b"tf-binary"})
        dest = tmp_path / "out"

        with patch(
            "tools.doit.install_tools.urllib.request.urlretrieve",
            side_effect=lambda url, d: shutil.copy(fixture, d),
        ):
            result = download_and_extract_archive(
                "https://github.com/o/r/releases/download/v1/terraform.zip", ["terraform"], dest
            )

        assert (dest / "terraform").read_bytes() == b"tf-binary"
        assert result == [dest / "terraform"]

    def test_ignores_extra_files_in_archive(self, tmp_path: Path) -> None:
        fixture = tmp_path / "fixture.tar.gz"
        _make_targz(
            fixture,
            {
                "age/age": b"age",
                "age/LICENSE": b"license-text",
                "age/README.md": b"readme",
            },
        )
        dest = tmp_path / "out"

        with patch(
            "tools.doit.install_tools.urllib.request.urlretrieve",
            side_effect=lambda url, d: shutil.copy(fixture, d),
        ):
            download_and_extract_archive(
                "https://github.com/o/r/releases/download/v1/age.tar.gz", ["age"], dest
            )

        assert (dest / "age").exists()
        assert not (dest / "LICENSE").exists()
        assert not (dest / "README.md").exists()

    def test_blocks_path_traversal_in_tar(self, tmp_path: Path) -> None:
        fixture = tmp_path / "fixture.tar.gz"
        # Create a tar member that attempts to escape via parent dirs
        with tarfile.open(fixture, "w:gz") as tar:
            import io

            evil = b"pwned"
            info = tarfile.TarInfo(name="../../../etc/evil")
            info.size = len(evil)
            info.mode = 0o644
            tar.addfile(info, io.BytesIO(evil))
            good = b"good-binary"
            info2 = tarfile.TarInfo(name="bin/mytool")
            info2.size = len(good)
            info2.mode = 0o644
            tar.addfile(info2, io.BytesIO(good))

        dest = tmp_path / "out"

        with patch(
            "tools.doit.install_tools.urllib.request.urlretrieve",
            side_effect=lambda url, d: shutil.copy(fixture, d),
        ):
            download_and_extract_archive(
                "https://github.com/o/r/releases/download/v1/x.tar.gz", ["mytool"], dest
            )

        # Confirm no file landed outside dest_dir
        assert (dest / "mytool").exists()
        # The traversal target must not exist
        assert not Path("/etc/evil").exists()
        # And no "evil" file inside dest_dir
        assert not (dest / "evil").exists()

    def test_unsupported_extension_raises_value_error(self, tmp_path: Path) -> None:
        with pytest.raises(ValueError, match="Unsupported archive extension"):
            download_and_extract_archive(
                "https://github.com/o/r/releases/download/v1/foo.7z", ["foo"], tmp_path
            )

    @pytest.fixture
    def private_tempdir(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
        """Point `tempfile` at a directory only the calling test writes to.

        The cleanup tests below assert on what is left behind in the temp
        directory. Reading the process-global one means reading a directory
        every other xdist worker is also writing to: ten tests in this file call
        `download_and_extract_archive`, and one of them mid-download drops a
        `tmpXXXX.tar.gz` inside the measurement window, which the diff then
        attributes to the test doing the measuring (#756).

        `download_and_extract_archive` creates its scratch archive with
        `tempfile.NamedTemporaryFile`, which resolves `tempfile.tempdir` at call
        time, so redirecting it here covers the implementation and the
        assertion together. The scope is this process, and xdist workers are
        separate processes, so nothing leaks between them.
        """
        private = tmp_path / "systemp"
        private.mkdir()
        monkeypatch.setattr(tempfile, "tempdir", str(private))
        return private

    def test_temp_file_cleanup_on_success(self, tmp_path: Path, private_tempdir: Path) -> None:
        fixture = tmp_path / "fixture.tar.gz"
        _make_targz(fixture, {"mytool": b"binary"})
        dest = tmp_path / "out"

        before = set(private_tempdir.iterdir())
        with patch(
            "tools.doit.install_tools.urllib.request.urlretrieve",
            side_effect=lambda url, d: shutil.copy(fixture, d),
        ):
            download_and_extract_archive(
                "https://github.com/o/r/releases/download/v1/x.tar.gz", ["mytool"], dest
            )
        after = set(private_tempdir.iterdir())

        new_files = after - before
        assert not new_files, f"download_and_extract_archive left {sorted(new_files)} behind"

    def test_temp_file_cleanup_on_failure(self, tmp_path: Path, private_tempdir: Path) -> None:
        fixture = tmp_path / "fixture.tar.gz"
        _make_targz(fixture, {"other": b"binary"})
        dest = tmp_path / "out"

        before = set(private_tempdir.iterdir())
        with (
            patch(
                "tools.doit.install_tools.urllib.request.urlretrieve",
                side_effect=lambda url, d: shutil.copy(fixture, d),
            ),
            pytest.raises(RuntimeError, match="not found in archive"),
        ):
            download_and_extract_archive(
                "https://github.com/o/r/releases/download/v1/x.tar.gz", ["missing"], dest
            )
        after = set(private_tempdir.iterdir())

        new_files = after - before
        assert not new_files, f"download_and_extract_archive left {sorted(new_files)} behind"

    def test_missing_binary_raises_runtime_error(self, tmp_path: Path) -> None:
        fixture = tmp_path / "fixture.tar.gz"
        _make_targz(fixture, {"present": b"x"})
        dest = tmp_path / "out"

        with (
            patch(
                "tools.doit.install_tools.urllib.request.urlretrieve",
                side_effect=lambda url, d: shutil.copy(fixture, d),
            ),
            pytest.raises(RuntimeError, match="absent"),
        ):
            download_and_extract_archive(
                "https://github.com/o/r/releases/download/v1/x.tar.gz", ["absent"], dest
            )

    @pytest.mark.skipif(
        sys.platform == "win32", reason="Windows does not support Unix file permissions"
    )
    def test_chmod_755_on_extracted(self, tmp_path: Path) -> None:
        fixture = tmp_path / "fixture.zip"
        _make_zip(fixture, {"mytool": b"binary"})
        dest = tmp_path / "out"

        with patch(
            "tools.doit.install_tools.urllib.request.urlretrieve",
            side_effect=lambda url, d: shutil.copy(fixture, d),
        ):
            download_and_extract_archive(
                "https://github.com/o/r/releases/download/v1/x.zip", ["mytool"], dest
            )

        assert (dest / "mytool").stat().st_mode & 0o755 == 0o755


class TestDownloadIntegrity:
    """Integrity verification for downloaded binaries and archives (#694).

    The framework runs what it downloads: binaries get `chmod 0o755`, archives
    get parsed and extracted. Nothing verified what arrived. These tests cover
    the two halves of the rule — a digest is checked when given, and is
    mandatory for hosts outside `IMPLICITLY_TRUSTED_HOSTS`.

    What this deliberately does *not* claim: fetching a checksum file from the
    same origin as the asset would defend against almost nothing, since TLS
    already covers the transport and an attacker who can replace the asset can
    replace the checksum. The value here is that a caller reaching an arbitrary
    third party must state what it expects.
    """

    def test_sha256_of_matches_hashlib(self, tmp_path: Path) -> None:
        """The digest helper must agree with hashlib on real bytes."""
        target = tmp_path / "blob"
        target.write_bytes(b"integrity" * 5000)

        assert sha256_of(target) == hashlib.sha256(b"integrity" * 5000).hexdigest()

    def test_digest_spans_the_whole_file(self, tmp_path: Path) -> None:
        """Chunked reading must not stop at the first chunk.

        A helper that hashed only the first block would pass every test above
        while accepting a file whose tail had been replaced.
        """
        big = b"A" * (1024 * 1024 * 2 + 17)
        tampered = big[:-1] + b"B"
        a, b = tmp_path / "a", tmp_path / "b"
        a.write_bytes(big)
        b.write_bytes(tampered)

        assert sha256_of(a) != sha256_of(b)

    @pytest.mark.parametrize(
        ("url", "required"),
        [
            ("https://github.com/o/r/releases/download/v1/tool", False),
            ("https://objects.githubusercontent.com/x", False),
            ("https://releases.hashicorp.com/terraform/1.5.0/x.zip", True),
            ("https://evil.example/tool", True),
            ("https://github.com.evil.example/tool", True),
            ("https://notgithub.com/tool", True),
        ],
    )
    def test_requires_digest_by_host(self, url: str, required: bool) -> None:
        """Host policy is decided on the parsed hostname, not a substring."""
        assert requires_digest(url) is required

    def test_matching_digest_passes_and_keeps_the_file(self, tmp_path: Path) -> None:
        target = tmp_path / "tool"
        target.write_bytes(b"payload")

        verify_download(target, "https://evil.example/tool", sha256_of(target))

        assert target.exists()

    def test_mismatch_raises_and_deletes_the_file(self, tmp_path: Path) -> None:
        """Fail closed: nothing is left on disk for a caller to run."""
        target = tmp_path / "tool"
        target.write_bytes(b"malicious")

        with pytest.raises(IntegrityError, match="Integrity check failed"):
            verify_download(target, "https://github.com/o/r/x", "0" * 64)

        assert not target.exists(), "a file that failed verification must not survive"

    def test_missing_digest_on_untrusted_host_raises_and_deletes(self, tmp_path: Path) -> None:
        target = tmp_path / "tool"
        target.write_bytes(b"whatever")

        with pytest.raises(IntegrityError, match="no sha256 was given"):
            verify_download(target, "https://releases.hashicorp.com/x", None)

        assert not target.exists()

    def test_missing_digest_on_github_is_allowed(self, tmp_path: Path) -> None:
        """GitHub assets keep working without a digest — no behaviour change."""
        target = tmp_path / "tool"
        target.write_bytes(b"gh-asset")

        verify_download(target, "https://github.com/cli/cli/releases/download/v1/gh", None)

        assert target.exists()

    def test_digest_comparison_ignores_case_and_whitespace(self, tmp_path: Path) -> None:
        """Digests copied from checksum files carry stray case and spacing."""
        target = tmp_path / "tool"
        target.write_bytes(b"payload")
        expected = sha256_of(target)

        verify_download(target, "https://evil.example/tool", f"  {expected.upper()}\n")

        assert target.exists()

    def test_archive_is_not_parsed_when_the_digest_is_wrong(self, tmp_path: Path) -> None:
        """Verification must happen before the archive is opened.

        Extraction is hardened, but not parsing a known-bad archive at all is
        strictly better than relying on that hardening.
        """
        fixture = tmp_path / "fixture.tar.gz"
        _make_targz(fixture, {"tool": b"binary"})
        dest = tmp_path / "out"

        with (
            patch(
                "tools.doit.install_tools.urllib.request.urlretrieve",
                side_effect=lambda url, d: shutil.copy(fixture, d),
            ),
            patch("tools.doit.install_tools.tarfile.open") as mock_tar,
            pytest.raises(IntegrityError, match="Integrity check failed"),
        ):
            download_and_extract_archive(
                "https://github.com/o/r/x.tar.gz", ["tool"], dest, sha256="0" * 64
            )

        mock_tar.assert_not_called()
        assert not dest.exists() or not any(dest.iterdir())

    def test_binary_is_not_made_executable_when_the_digest_is_wrong(self, tmp_path: Path) -> None:
        """A file that fails verification must never get the executable bit."""
        install_dir = tmp_path / "bin"
        install_dir.mkdir()

        with (
            patch("tools.doit.install_tools.get_install_dir", return_value=install_dir),
            patch(
                "tools.doit.install_tools.urllib.request.urlretrieve",
                side_effect=lambda url, dest: Path(dest).write_bytes(b"tampered"),
            ),
            pytest.raises(IntegrityError, match="Integrity check failed"),
        ):
            download_github_release_binary(
                repo="o/r",
                version="1.0.0",
                asset_pattern="tool",
                dest_name="tool",
                sha256="0" * 64,
            )

        assert not (install_dir / "tool").exists()
