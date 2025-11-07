#!/bin/bash
# Linting script for bastproxy

echo "Running Ruff linting..."
echo "======================"

# Run ruff check
ruff check . "$@"

exit_code=$?

if [ $exit_code -eq 0 ]; then
    echo ""
    echo "✓ Linting passed!"
else
    echo ""
    echo "✗ Linting found issues"
    echo ""
    echo "Run 'ruff check . --fix' to auto-fix some issues"
fi

exit $exit_code
