"""Configuration fixtures for BastProxy integration tests.

This module provides pytest fixtures for setting up and tearing down
the BastProxy server, managing telnet connections, and handling
authentication. These fixtures enable integration testing by running
the proxy in a subprocess and connecting to it via telnet.

Key Fixtures:
    - proxy_port: The port number for test proxy instance (19999).
    - clean_proxy_config: Deletes proxy config to reset to defaults.
    - proxy_server: Starts proxy subprocess and manages its lifecycle.
    - telnet_connection: Opens telnet connection to running proxy.
    - authenticated_client: Provides authenticated telnet connection.

"""

import asyncio
import shutil
import time
from collections.abc import AsyncGenerator
from pathlib import Path

import pytest
import pytest_asyncio
import telnetlib3

# Constants for integration tests
PROXY_PORT = 19999
PROXY_STARTUP_TIMEOUT = 20
DEFAULT_PASSWORD = "defaultpass"


@pytest.fixture(scope="session")
def proxy_port() -> int:
    """Provide the port number for the test proxy instance.

    Returns:
        The port number (19999) to use for integration tests.

    """
    return PROXY_PORT


@pytest.fixture
def _clean_proxy_config() -> None:
    """Delete the proxy configuration directory.

    This fixture removes the proxy plugin configuration to ensure
    tests start with default settings (including default password).

    Returns:
        None

    """
    config_dir = Path("data/plugins/plugins.core.proxy")
    if config_dir.exists():
        shutil.rmtree(config_dir)


@pytest_asyncio.fixture
async def proxy_server(
    _clean_proxy_config: None, proxy_port: int
) -> AsyncGenerator[asyncio.subprocess.Process, None]:
    """Start the proxy server in a subprocess for testing.

    This fixture starts the BastProxy server on the specified port,
    waits for it to be ready, yields the process for tests, and
    then terminates it during cleanup.

    Args:
        clean_proxy_config: Fixture that cleans configuration.
        proxy_port: The port to run the proxy on.

    Yields:
        The subprocess.Process object for the running proxy server.

    """
    # Start the proxy server (must run from repo root)
    process = await asyncio.create_subprocess_exec(
        "python3",
        "mudproxy.py",
        "-p",
        str(proxy_port),
        "--quiet",
        stdout=asyncio.subprocess.DEVNULL,
        stderr=asyncio.subprocess.DEVNULL,
        cwd=Path(__file__).parent.parent.parent,
    )

    # Wait for the server to start accepting connections
    start_time = time.time()
    while time.time() - start_time < PROXY_STARTUP_TIMEOUT:
        try:
            _, test_writer = await asyncio.wait_for(
                telnetlib3.open_connection("localhost", proxy_port), timeout=1.0
            )
            if test_writer:
                test_writer.close()
            break
        except (ConnectionRefusedError, TimeoutError, OSError):
            await asyncio.sleep(0.5)
    else:
        process.terminate()
        await process.wait()
        msg = f"Proxy server failed to start within {PROXY_STARTUP_TIMEOUT}s"
        raise TimeoutError(msg)

    yield process

    # Cleanup: terminate the proxy
    process.terminate()
    try:
        await asyncio.wait_for(process.wait(), timeout=5.0)
    except TimeoutError:
        process.kill()
        await process.wait()


@pytest_asyncio.fixture
async def telnet_connection(
    proxy_server: asyncio.subprocess.Process, proxy_port: int
) -> AsyncGenerator[tuple, None]:
    """Open a telnet connection to the running proxy.

    This fixture establishes a telnet connection and provides the
    reader and writer objects for communication.

    Args:
        proxy_server: The running proxy server process.
        proxy_port: The port the proxy is listening on.

    Yields:
        A tuple of (reader, writer) for the telnet connection.

    """
    reader, writer = await telnetlib3.open_connection("localhost", proxy_port)

    yield reader, writer

    # Close the connection
    if writer:
        writer.close()


@pytest_asyncio.fixture
async def authenticated_client(telnet_connection: tuple) -> tuple:
    """Provide an authenticated telnet connection.

    This fixture reads the banner, sends the default password, and
    verifies authentication succeeded.

    Args:
        telnet_connection: The telnet connection fixture.

    Returns:
        A tuple of (reader, writer) with authenticated session.

    Raises:
        RuntimeError: If authentication fails.

    """
    reader, writer = telnet_connection

    # Read the banner/password prompt
    await asyncio.wait_for(reader.read(2048), timeout=2.0)

    # Send the default password
    writer.write(f"{DEFAULT_PASSWORD}\n")
    await writer.drain()

    # Read authentication response
    auth_response = await asyncio.wait_for(reader.read(2048), timeout=2.0)

    # Verify we logged in successfully
    if b"logged in" not in auth_response.lower():
        msg = f"Authentication failed: {auth_response}"
        raise RuntimeError(msg)

    return reader, writer
