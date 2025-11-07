# Security Policy

## Reporting Security Vulnerabilities

If you discover a security vulnerability in BastProxy, please report it by emailing the maintainers. Please do not create public GitHub issues for security vulnerabilities.

## Security Scanning

BastProxy uses automated security scanning tools:

### Bandit (Static Code Analysis)
- Scans Python code for common security issues
- Runs on every push to main/develop branches
- Weekly scheduled scans
- **Current Status**: 2 known issues in test plugins (eval() usage - non-production code)

### Safety (Dependency Vulnerability Scanning)
- Checks dependencies for known security vulnerabilities
- Runs on every push and weekly
- **Current Status**: No known vulnerabilities

## Known Issues and Exceptions

### Telnet Protocol (B401)
**Status**: Accepted Risk
**Reason**: BastProxy is a MUD (Multi-User Dungeon) proxy that must use the Telnet protocol to communicate with game servers. MUDs use Telnet as their standard protocol.
**Mitigation**:
- Only connects to user-specified MUD servers
- Does not accept arbitrary telnet connections from untrusted sources
- Client connections can be restricted by IP

### Shell Parameter (B604)
**Status**: False Positive
**Reason**: The `shell` parameter in telnetlib3 refers to a connection handler function, not OS shell commands.
**Mitigation**: N/A - Not actually a shell command execution risk

### eval() in Test Plugins (B307)
**Status**: Accepted - Test Code Only
**Location**: `plugins/test/newmon/`
**Reason**: Test plugin for development purposes, not loaded in production
**Mitigation**: Test plugins should not be loaded in production environments

## Security Best Practices

When developing for BastProxy:

1. **Input Validation**: Always validate and sanitize user input
2. **SQL Queries**: Use parameterized queries (never string formatting)
3. **File Operations**: Validate file paths and use safe path operations
4. **Network Data**: Treat all network data as untrusted
5. **Logging**: Never log sensitive information (passwords, tokens)
6. **Dependencies**: Keep dependencies updated regularly

## Running Security Scans Locally

```bash
# Run full security scan
./scripts/security-scan.sh

# Run Bandit only
bandit -r libs/ plugins/ --skip B401,B604 -ll

# Run Safety only
safety scan
```

## Dependency Updates

We monitor dependencies for security vulnerabilities and update promptly when issues are discovered. Dependencies are checked:
- Automatically on every PR via GitHub Actions
- Weekly via scheduled workflow
- Manually when security advisories are published

## Secure Configuration

When deploying BastProxy:

1. **Network**: Use firewall rules to restrict access
2. **Passwords**: Never commit passwords or tokens to version control
3. **Data Directory**: Protect data directory with appropriate file permissions
4. **Logs**: Regularly rotate and secure log files
5. **Updates**: Keep BastProxy and dependencies updated

## Security Update Process

1. Security issue identified (automated scan or manual report)
2. Issue triaged and severity assessed
3. Fix developed and tested
4. Security advisory published (for high/critical issues)
5. Release with fix deployed
6. Users notified via GitHub releases

## Contact

For security concerns, contact the maintainers via GitHub.
