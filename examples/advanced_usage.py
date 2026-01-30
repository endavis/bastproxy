#!/usr/bin/env python3
"""Advanced usage example for bastproxy.

This example demonstrates advanced features and best practices.
"""

import logging
from pathlib import Path

from bastproxy import __version__

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


class AdvancedExample:
    """Example class demonstrating advanced usage patterns."""

    def __init__(self, config: dict[str, str] | None = None):
        """Initialize with optional configuration.

        Args:
            config: Optional configuration dictionary
        """
        self.config = config or {}
        logger.info("Initialized AdvancedExample with config: %s", self.config)

    def process_file(self, file_path: Path) -> dict[str, int]:
        """Process a file and return statistics.

        Args:
            file_path: Path to file to process

        Returns:
            Dictionary with file statistics
        """
        logger.info("Processing file: %s", file_path)

        # Example file processing
        stats = {
            "lines": 0,
            "words": 0,
            "chars": 0,
        }

        try:
            if file_path.exists():
                content = file_path.read_text()
                stats["lines"] = len(content.splitlines())
                stats["words"] = len(content.split())
                stats["chars"] = len(content)
        except Exception as e:
            logger.error("Failed to process file: %s", e)
            raise

        return stats

    def batch_process(self, files: list[Path]) -> list[dict[str, int]]:
        """Process multiple files.

        Args:
            files: List of file paths

        Returns:
            List of statistics for each file
        """
        results = []
        for file_path in files:
            try:
                stats = self.process_file(file_path)
                results.append(stats)
            except Exception as e:
                logger.warning("Skipping file %s due to error: %s", file_path, e)
                continue

        return results


def main():
    """Run advanced usage examples."""
    print(f"Advanced Examples - bastproxy v{__version__}")
    print("=" * 60)
    print()

    # Example 1: Configuration
    print("Example 1: Advanced Configuration")
    print("-" * 60)
    config = {
        "option1": "value1",
        "option2": "value2",
    }
    example = AdvancedExample(config=config)
    print(f"Created instance with config: {config}")
    print()

    # Example 2: File processing
    print("Example 2: File Processing")
    print("-" * 60)
    # Create a temporary file for demonstration
    temp_file = Path("temp_example.txt")
    temp_file.write_text("Hello, World!\nThis is a test file.")

    stats = example.process_file(temp_file)
    print(f"File statistics: {stats}")

    # Clean up
    temp_file.unlink()
    print()

    # Example 3: Batch processing
    print("Example 3: Batch Processing")
    print("-" * 60)
    # Create multiple temporary files
    files = []
    for i in range(3):
        file_path = Path(f"temp_{i}.txt")
        file_path.write_text(f"File {i}\n" * (i + 1))
        files.append(file_path)

    results = example.batch_process(files)
    for i, stats in enumerate(results):
        print(f"File {i}: {stats}")

    # Clean up
    for file_path in files:
        file_path.unlink()
    print()

    # Example 4: Context manager usage
    print("Example 4: Best Practices")
    print("-" * 60)
    print("Using context managers for resource management:")
    # TODO: Add context manager example if your package supports it
    # with YourResource() as resource:
    #     result = resource.do_something()
    print("Resources automatically cleaned up!")
    print()

    print("All advanced examples completed!")


if __name__ == "__main__":
    main()
