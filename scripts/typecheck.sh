#!/bin/bash
# Type checking script for bastproxy

echo "Running mypy type checking..."
echo "=============================="

# Run mypy on main modules
mypy mudproxy.py libs/ plugins/ --exclude 'plugins/test' --exclude 'tests'

exit_code=$?

if [ $exit_code -eq 0 ]; then
    echo ""
    echo "✓ Type checking passed!"
else
    echo ""
    echo "✗ Type checking found issues"
fi

exit $exit_code
