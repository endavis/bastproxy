#!/bin/bash
# Security scanning script for BastProxy

set -e

echo "================================"
echo "Running Bandit Security Scan"
echo "================================"
echo ""

# Run Bandit with appropriate exclusions
# B401: telnet imports - MUD proxy requires telnet for game server communication
# B604: shell parameter - telnetlib3 uses 'shell' for connection handlers, not OS shell commands
# B110: try/except/pass - acceptable in some contexts (will review medium+ manually)
# B608: SQL injection - using parameterized queries, false positive

bandit -r libs/ plugins/ \
    --skip B401,B604 \
    --exclude ./tests/,./venv/,./evennia/,./data/,./teststuff/ \
    --format txt \
    --severity-level medium \
    --confidence-level medium

echo ""
echo "================================"
echo "Running Safety Dependency Scan"
echo "================================"
echo ""

# Run Safety to check for known vulnerabilities in dependencies
safety scan --output text 2>&1 || true

echo ""
echo "================================"
echo "Security Scan Complete"
echo "================================"
