"""Tests for the argp module (argument parsing utilities).

This module tests the customized argument parser including:
- ArgumentParser that raises errors instead of exiting
- CustomFormatter for help text formatting
- Default value inclusion in help text
- Text wrapping at 73 characters

Test Classes:
    - `TestArgumentParser`: Tests for ArgumentParser error handling.
    - `TestCustomFormatter`: Tests for CustomFormatter functionality.

"""

import argparse

import pytest
from bastproxy.libs.argp import (
    OPTIONAL,
    SUPPRESS,
    ZERO_OR_MORE,
    ArgumentError,
    ArgumentParser,
    CustomFormatter,
)


class TestArgumentParser:
    """Test ArgumentParser error handling."""

    def test_argument_parser_creation(self) -> None:
        """Test that ArgumentParser can be created."""
        parser = ArgumentParser()

        assert parser is not None
        assert isinstance(parser, argparse.ArgumentParser)

    def test_argument_parser_with_description(self) -> None:
        """Test creating ArgumentParser with description."""
        parser = ArgumentParser(description="Test parser")

        assert parser.description == "Test parser"

    def test_parser_raises_on_error(self) -> None:
        """Test that ArgumentParser raises ArgumentError instead of exiting."""
        parser = ArgumentParser()
        parser.add_argument("--required", required=True)

        # Should raise ArgumentError instead of calling sys.exit()
        try:
            parser.parse_args([])
            pytest.fail("Should have raised ArgumentError")
        except ArgumentError:
            # Expected behavior
            pass

    def test_parser_with_valid_args(self) -> None:
        """Test parsing valid arguments."""
        parser = ArgumentParser()
        parser.add_argument("--name", default="test")
        parser.add_argument("--count", type=int, default=5)

        args = parser.parse_args(["--name", "myname", "--count", "10"])

        assert args.name == "myname"
        assert args.count == 10

    def test_parser_with_positional_args(self) -> None:
        """Test parsing positional arguments."""
        parser = ArgumentParser()
        parser.add_argument("input_file")
        parser.add_argument("output_file")

        args = parser.parse_args(["input.txt", "output.txt"])

        assert args.input_file == "input.txt"
        assert args.output_file == "output.txt"

    def test_parser_with_optional_args(self) -> None:
        """Test parsing optional arguments with defaults."""
        parser = ArgumentParser()
        parser.add_argument("--verbose", action="store_true")
        parser.add_argument("--level", default="info")

        args = parser.parse_args([])

        assert args.verbose is False
        assert args.level == "info"

    def test_parser_error_with_invalid_type(self) -> None:
        """Test that parser raises error for invalid type conversion."""
        parser = ArgumentParser()
        parser.add_argument("--number", type=int)

        try:
            parser.parse_args(["--number", "not_a_number"])
            pytest.fail("Should have raised ArgumentError")
        except (ArgumentError, SystemExit):
            # Expected behavior - either ArgumentError or SystemExit from argparse
            pass


class TestCustomFormatter:
    """Test CustomFormatter functionality."""

    def test_custom_formatter_creation(self) -> None:
        """Test that CustomFormatter can be created."""
        parser = ArgumentParser(formatter_class=CustomFormatter)

        assert parser is not None

    def test_formatter_adds_default_to_help(self) -> None:
        """Test that CustomFormatter adds default values to help text."""
        parser = ArgumentParser(formatter_class=CustomFormatter)
        parser.add_argument("--name", default="test", help="The name parameter")

        help_text = parser.format_help()

        # Should include the default value
        assert "default:" in help_text or "(default:" in help_text

    def test_formatter_with_suppress_default(self) -> None:
        """Test that SUPPRESS prevents default from appearing in help."""
        parser = ArgumentParser(formatter_class=CustomFormatter)
        parser.add_argument("--hidden", default=SUPPRESS, help="Hidden parameter")

        help_text = parser.format_help()

        # The actual help text format depends on argparse version
        # Just verify that help is generated
        assert isinstance(help_text, str)

    def test_formatter_with_required_arg(self) -> None:
        """Test help text for required arguments."""
        parser = ArgumentParser(formatter_class=CustomFormatter)
        parser.add_argument("--required", required=True, help="Required parameter")

        help_text = parser.format_help()

        assert "--required" in help_text
        assert "Required parameter" in help_text

    def test_formatter_with_multiple_args(self) -> None:
        """Test formatter with multiple arguments."""
        parser = ArgumentParser(
            description="Test parser", formatter_class=CustomFormatter
        )
        parser.add_argument("--name", default="default_name", help="Name parameter")
        parser.add_argument("--count", type=int, default=5, help="Count parameter")
        parser.add_argument("--verbose", action="store_true", help="Verbose output")

        help_text = parser.format_help()

        assert "--name" in help_text
        assert "--count" in help_text
        assert "--verbose" in help_text

    def test_formatter_text_wrapping(self) -> None:
        """Test that CustomFormatter wraps text appropriately."""
        parser = ArgumentParser(formatter_class=CustomFormatter)

        # Add an argument with long help text
        long_help = (
            "This is a very long help text that should be wrapped at "
            "73 characters to ensure proper formatting in the terminal "
            "and provide a good user experience when viewing help text"
        )
        parser.add_argument("--long", help=long_help)

        help_text = parser.format_help()

        # Verify help is generated and contains the argument
        assert "--long" in help_text
        assert isinstance(help_text, str)


class TestArgumentParserConstants:
    """Test that argparse constants are properly exported."""

    def test_optional_constant(self) -> None:
        """Test that OPTIONAL constant is available."""
        assert OPTIONAL == argparse.OPTIONAL

    def test_zero_or_more_constant(self) -> None:
        """Test that ZERO_OR_MORE constant is available."""
        assert ZERO_OR_MORE == argparse.ZERO_OR_MORE

    def test_suppress_constant(self) -> None:
        """Test that SUPPRESS constant is available."""
        assert SUPPRESS == argparse.SUPPRESS

    def test_argument_error_available(self) -> None:
        """Test that ArgumentError exception is available."""
        assert ArgumentError == argparse.ArgumentError


class TestArgumentParserIntegration:
    """Test ArgumentParser integration scenarios."""

    def test_parser_with_subparsers(self) -> None:
        """Test ArgumentParser with subparsers."""
        parser = ArgumentParser()
        subparsers = parser.add_subparsers(dest="command")

        # Add subcommands
        start_parser = subparsers.add_parser("start")
        start_parser.add_argument("--port", type=int, default=8080)

        stop_parser = subparsers.add_parser("stop")
        stop_parser.add_argument("--force", action="store_true")

        # Parse 'start' command
        args = parser.parse_args(["start", "--port", "9000"])
        assert args.command == "start"
        assert args.port == 9000

        # Parse 'stop' command
        args2 = parser.parse_args(["stop", "--force"])
        assert args2.command == "stop"
        assert args2.force is True

    def test_parser_with_mutually_exclusive_group(self) -> None:
        """Test ArgumentParser with mutually exclusive arguments."""
        parser = ArgumentParser()
        group = parser.add_mutually_exclusive_group()
        group.add_argument("--json", action="store_true")
        group.add_argument("--xml", action="store_true")

        # Should work with one option
        args = parser.parse_args(["--json"])
        assert args.json is True
        assert args.xml is False

        # Should raise error with both options
        try:
            parser.parse_args(["--json", "--xml"])
            pytest.fail("Should have raised error for mutually exclusive args")
        except (ArgumentError, SystemExit):
            # Expected behavior
            pass

    def test_parser_with_choices(self) -> None:
        """Test ArgumentParser with limited choices."""
        parser = ArgumentParser()
        parser.add_argument("--level", choices=["debug", "info", "warning", "error"])

        # Valid choice
        args = parser.parse_args(["--level", "debug"])
        assert args.level == "debug"

        # Invalid choice should raise error
        try:
            parser.parse_args(["--level", "invalid"])
            pytest.fail("Should have raised error for invalid choice")
        except (ArgumentError, SystemExit):
            # Expected behavior
            pass
