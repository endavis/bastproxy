# Integration Tests

This directory contains integration tests for BastProxy that connect to a running proxy instance via telnet.

## Status

**These tests are currently experimental.**

The integration test framework has been created with fixtures for:
- Starting/stopping proxy server in subprocess
- Opening telnet connections
- Authenticating with default password
- Testing commands and responses

## Features

- **Quiet Mode**: The proxy supports a `--quiet` flag that suppresses console output while still logging to file
- **Subprocess Management**: Tests start the proxy in a subprocess for isolation
- **Automatic Cleanup**: Proxy processes are terminated after each test

## Known Issues

The current implementation has challenges with:
1. Proxy startup time (~6-7 seconds) requiring longer timeouts (20s configured)
2. Test hanging/timeout issues with pytest-asyncio subprocess management
3. Event loop integration between pytest-asyncio and telnetlib3

## Future Work

To make these tests production-ready:
1. Fix subprocess management to properly wait for server readiness
2. Add retry logic for connection attempts with better error handling
3. Consider alternative approaches (e.g., direct API testing without subprocess)

## Files

- `conftest.py`: Pytest fixtures for proxy lifecycle management
- `test_proxy_integration.py`: Integration test cases (9 tests)

## Running Tests

```bash
# These tests are currently disabled
# pytest tests/integration/ -v
```

For now, continue using the 179 unit tests for validation:
```bash
pytest tests/ -k "not integration" -v
```
