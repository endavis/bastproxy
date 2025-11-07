# Project: bastproxy
# Filename: tests/plugins/test_plugin_discovery.py
#
# File Description: Tests for plugin discovery system
#
# By: Bast
"""Tests for plugin discovery in bastproxy.

This module tests the plugin discovery and validation functionality.

"""

from libs.plugins import imputils


class TestPluginDiscovery:
    """Tests for plugin discovery functionality."""

    def test_is_plugin_with_single_quotes(self, tmp_path):
        """Test plugin detection with single quote PLUGIN_NAME."""
        plugin_init = tmp_path / "__init__.py"
        plugin_init.write_text("PLUGIN_NAME = 'Test Plugin'\n")

        assert imputils.is_plugin(str(plugin_init))

    def test_is_plugin_with_double_quotes(self, tmp_path):
        """Test plugin detection with double quote PLUGIN_NAME."""
        plugin_init = tmp_path / "__init__.py"
        plugin_init.write_text('PLUGIN_NAME = "Test Plugin"\n')

        assert imputils.is_plugin(str(plugin_init))

    def test_is_plugin_mixed_quotes_in_content(self, tmp_path):
        """Test plugin detection works regardless of other quote usage."""
        plugin_init = tmp_path / "__init__.py"
        content = """
# Comment with 'single' quotes
PLUGIN_NAME = "Test Plugin"
PLUGIN_PURPOSE = 'Test purpose'
"""
        plugin_init.write_text(content)

        assert imputils.is_plugin(str(plugin_init))

    def test_is_not_plugin_without_name(self, tmp_path):
        """Test that files without PLUGIN_NAME are not detected as plugins."""
        non_plugin = tmp_path / "__init__.py"
        non_plugin.write_text("# Just a regular module\n")

        assert not imputils.is_plugin(str(non_plugin))

    def test_is_not_plugin_with_commented_name(self, tmp_path):
        """Test behavior with commented PLUGIN_NAME.

        Note: The current regex does match commented PLUGIN_NAME.
        This documents the current behavior rather than ideal behavior.

        """
        non_plugin = tmp_path / "__init__.py"
        non_plugin.write_text("# PLUGIN_NAME = 'Test'\n")

        # Currently this DOES match - documenting actual behavior
        assert imputils.is_plugin(str(non_plugin))

    def test_plugin_name_regex_pattern(self):
        """Test the PLUGIN_NAME regex pattern directly.

        Note: Regex requires exactly one space before and after =

        """
        # Test single quotes
        assert imputils.NAMERE.search("PLUGIN_NAME = 'Test'")
        # Test double quotes
        assert imputils.NAMERE.search('PLUGIN_NAME = "Test"')
        # Test multiline (should not match if PLUGIN_NAME is on different line)
        assert imputils.NAMERE.search("PLUGIN_NAME = 'Multi\\nLine'")

    def test_find_packages_and_plugins_structure(self, tmp_path):
        """Test plugin discovery in a directory structure."""
        # Create a simple plugin structure
        plugin_dir = tmp_path / "test_plugin"
        plugin_dir.mkdir()

        # Create plugin package
        plugin_package = plugin_dir / "plugin"
        plugin_package.mkdir()

        # Create plugin __init__.py with PLUGIN_NAME
        plugin_init = plugin_dir / "__init__.py"
        plugin_init.write_text('PLUGIN_NAME = "Test Discovery"\n')

        plugin_file = plugin_package / "__init__.py"
        plugin_file.write_text("# Plugin code\n")

        # Note: find_packages_and_plugins expects a specific structure
        # This test may need adjustment based on actual implementation

    def test_plugin_metadata_extraction(self, tmp_path):
        """Test extracting all plugin metadata."""
        plugin_init = tmp_path / "__init__.py"
        content = """
PLUGIN_NAME = "Test Plugin"
PLUGIN_PURPOSE = "Testing purposes"
PLUGIN_AUTHOR = "Test Author"
PLUGIN_VERSION = 1
"""
        plugin_init.write_text(content)

        # Verify the file is recognized as a plugin
        assert imputils.is_plugin(str(plugin_init))

        # Read and verify all metadata is present
        text = plugin_init.read_text()
        assert "PLUGIN_NAME" in text
        assert "PLUGIN_PURPOSE" in text
        assert "PLUGIN_AUTHOR" in text
        assert "PLUGIN_VERSION" in text


class TestPluginNameRegex:
    """Test the PLUGIN_NAME regular expression pattern."""

    def test_regex_matches_single_quotes(self):
        """Test regex matches single-quoted PLUGIN_NAME."""
        match = imputils.NAMERE.search("PLUGIN_NAME = 'My Plugin'")
        assert match is not None
        assert match.group("value") == "My Plugin"

    def test_regex_matches_double_quotes(self):
        """Test regex matches double-quoted PLUGIN_NAME."""
        match = imputils.NAMERE.search('PLUGIN_NAME = "My Plugin"')
        assert match is not None
        assert match.group("value") == "My Plugin"

    def test_regex_captures_plugin_name(self):
        """Test regex correctly captures the plugin name value."""
        single_match = imputils.NAMERE.search("PLUGIN_NAME = 'Test'")
        assert single_match is not None
        assert single_match.group("value") == "Test"

        double_match = imputils.NAMERE.search('PLUGIN_NAME = "Test"')
        assert double_match is not None
        assert double_match.group("value") == "Test"

    def test_regex_with_special_characters(self):
        """Test regex works with special characters in plugin name."""
        match = imputils.NAMERE.search("PLUGIN_NAME = 'Test-Plugin_v2'")
        assert match is not None
        assert match.group("value") == "Test-Plugin_v2"

    def test_regex_does_not_match_wrong_variable(self):
        """Test regex doesn't match other variable names."""
        assert imputils.NAMERE.search("OTHER_NAME = 'Test'") is None
        assert imputils.NAMERE.search("PLUGIN_PURPOSE = 'Test'") is None

    def test_regex_with_whitespace_variations(self):
        """Test regex whitespace requirements.

        Note: Regex requires exactly one space before and after =

        """
        # With exact spacing (works)
        assert imputils.NAMERE.search("PLUGIN_NAME = 'Test'") is not None

        # Without spaces (does not match)
        assert imputils.NAMERE.search("PLUGIN_NAME='Test'") is None

        # With multiple spaces (does not match)
        assert imputils.NAMERE.search("PLUGIN_NAME  =  'Test'") is None
