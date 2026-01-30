#!/usr/bin/env python3
"""CLI usage example for bastproxy.

This example demonstrates how to use the command-line interface
programmatically and provides examples of CLI commands.
"""

import subprocess
import sys
from pathlib import Path


def run_command(cmd: list[str]) -> tuple[int, str, str]:
    """Run a CLI command and return results.

    Args:
        cmd: Command and arguments as list

    Returns:
        Tuple of (return_code, stdout, stderr)
    """
    print(f"Running: {' '.join(cmd)}")
    result = subprocess.run(cmd, capture_output=True, text=True)
    return result.returncode, result.stdout, result.stderr


def main():
    """Run CLI usage examples."""
    print("CLI Usage Examples")
    print("=" * 60)
    print()

    # Check if CLI is available
    cli_cmd = "package-cli"  # Replace with your actual CLI command

    # Example 1: Show help
    print("Example 1: Show Help")
    print("-" * 60)
    print(f"Command: {cli_cmd} --help")
    print()
    print("Expected output:")
    print("  Usage: package-cli [OPTIONS] COMMAND [ARGS]...")
    print("  Options:")
    print("    --help  Show this message and exit")
    print()

    # Example 2: Run a basic command
    print("Example 2: Basic Command")
    print("-" * 60)
    print(f"Command: {cli_cmd} command --option value")
    print()
    print("This would run a basic command with an option.")
    print()

    # Example 3: Process a file
    print("Example 3: Process File")
    print("-" * 60)
    temp_file = Path("temp_input.txt")
    temp_file.write_text("Sample input data")

    print(f"Command: {cli_cmd} process {temp_file}")
    print()
    print("This would process the input file and display results.")

    # Clean up
    if temp_file.exists():
        temp_file.unlink()
    print()

    # Example 4: Output formats
    print("Example 4: Output Formats")
    print("-" * 60)
    print(f"Command: {cli_cmd} command --format json")
    print(f"Command: {cli_cmd} command --format yaml")
    print(f"Command: {cli_cmd} command --format table")
    print()
    print("Different output formats for various use cases.")
    print()

    # Example 5: Verbose mode
    print("Example 5: Verbose Output")
    print("-" * 60)
    print(f"Command: {cli_cmd} --verbose command")
    print()
    print("Enables detailed logging for debugging.")
    print()

    # Programmatic usage example
    print("Example 6: Programmatic Usage")
    print("-" * 60)
    print("You can also call CLI commands from Python code:")
    print()
    print("```python")
    print("import subprocess")
    print()
    print("result = subprocess.run(")
    print(f"    ['{cli_cmd}', 'command', '--option', 'value'],")
    print("    capture_output=True,")
    print("    text=True,")
    print(")")
    print("print(result.stdout)")
    print("```")
    print()

    print("CLI examples completed!")
    print()
    print("Note: These are example commands. Replace with actual")
    print("      commands from your package's CLI interface.")


if __name__ == "__main__":
    main()
