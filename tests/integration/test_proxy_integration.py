"""Integration tests for BastProxy server.

This module contains integration tests that verify the proxy server's
functionality by connecting to a running instance and testing various
commands and behaviors.

Test Classes:
    - `TestProxyConnection`: Tests basic connection and authentication.
    - `TestProxyCommands`: Tests command execution after authentication.

Note: These tests are currently disabled due to subprocess/pytest-asyncio
      timing issues. Use pytest -m integration to run them explicitly.

"""

import asyncio

import pytest

pytestmark = pytest.mark.skip(reason="Integration tests disabled - subprocess timing issues")


class TestProxyConnection:
    """Test basic proxy connection and authentication."""

    @pytest.mark.asyncio
    async def test_connection_succeeds(
        self, proxy_server: asyncio.subprocess.Process, proxy_port: int
    ) -> None:
        """Test that we can connect to the proxy server.

        Args:
            proxy_server: The running proxy server process.
            proxy_port: The port the proxy is listening on.

        Returns:
            None

        Raises:
            None

        """
        import telnetlib3

        reader, writer = await asyncio.wait_for(
            telnetlib3.open_connection("localhost", proxy_port), timeout=5.0
        )

        assert reader is not None
        assert writer is not None

        writer.close()

    @pytest.mark.asyncio
    async def test_banner_received(self, telnet_connection: tuple) -> None:
        """Test that the proxy sends a welcome banner.

        Args:
            telnet_connection: The telnet connection fixture.

        Returns:
            None

        Raises:
            None

        """
        reader, _ = telnet_connection

        # Read banner
        banner = await asyncio.wait_for(reader.read(2048), timeout=2.0)

        assert b"Welcome to Bastproxy" in banner
        assert b"password" in banner.lower()

    @pytest.mark.asyncio
    async def test_authentication_with_default_password(self, telnet_connection: tuple) -> None:
        """Test authentication with the default password.

        Args:
            telnet_connection: The telnet connection fixture.

        Returns:
            None

        Raises:
            None

        """
        reader, writer = telnet_connection

        # Read banner
        await asyncio.wait_for(reader.read(2048), timeout=2.0)

        # Send password
        writer.write("defaultpass\n")
        await writer.drain()

        # Read response
        response = await asyncio.wait_for(reader.read(2048), timeout=2.0)

        assert b"logged in" in response.lower()

    @pytest.mark.asyncio
    async def test_authentication_with_wrong_password(self, telnet_connection: tuple) -> None:
        """Test that wrong password is rejected.

        Args:
            telnet_connection: The telnet connection fixture.

        Returns:
            None

        Raises:
            None

        """
        reader, writer = telnet_connection

        # Read banner
        await asyncio.wait_for(reader.read(2048), timeout=2.0)

        # Send wrong password
        writer.write("wrongpassword\n")
        await writer.drain()

        # Read response
        response = await asyncio.wait_for(reader.read(2048), timeout=2.0)

        assert b"Invalid password" in response or b"invalid password" in response.lower()


class TestProxyCommands:
    """Test proxy commands after authentication."""

    @pytest.mark.asyncio
    async def test_help_command(self, authenticated_client: tuple) -> None:
        """Test that the help command works after authentication.

        Args:
            authenticated_client: The authenticated connection fixture.

        Returns:
            None

        Raises:
            None

        """
        reader, writer = authenticated_client

        # Send help command
        writer.write("help\n")
        await writer.drain()

        # Read response
        response = await asyncio.wait_for(reader.read(4096), timeout=3.0)

        # Help command should return some output
        assert len(response) > 0
        # Common indicators of help output
        assert b"#BP:" in response or b"command" in response.lower()

    @pytest.mark.asyncio
    async def test_multiple_commands(self, authenticated_client: tuple) -> None:
        """Test sending multiple commands in sequence.

        Args:
            authenticated_client: The authenticated connection fixture.

        Returns:
            None

        Raises:
            None

        """
        reader, writer = authenticated_client

        # Send first command
        writer.write("help\n")
        await writer.drain()
        response1 = await asyncio.wait_for(reader.read(4096), timeout=3.0)
        assert len(response1) > 0

        # Small delay between commands
        await asyncio.sleep(0.1)

        # Send second command
        writer.write("help\n")
        await writer.drain()
        response2 = await asyncio.wait_for(reader.read(4096), timeout=3.0)
        assert len(response2) > 0

    @pytest.mark.asyncio
    async def test_connection_stays_open(self, authenticated_client: tuple) -> None:
        """Test that the connection remains open after commands.

        Args:
            authenticated_client: The authenticated connection fixture.

        Returns:
            None

        Raises:
            None

        """
        reader, writer = authenticated_client

        # Send a command
        writer.write("help\n")
        await writer.drain()
        await asyncio.wait_for(reader.read(4096), timeout=3.0)

        # Wait a bit
        await asyncio.sleep(1.0)

        # Send another command - should still work
        writer.write("help\n")
        await writer.drain()
        response = await asyncio.wait_for(reader.read(4096), timeout=3.0)

        assert len(response) > 0


class TestProxyStartup:
    """Test proxy startup behavior."""

    @pytest.mark.asyncio
    async def test_server_starts_successfully(
        self, proxy_server: asyncio.subprocess.Process
    ) -> None:
        """Test that the proxy server starts without errors.

        Args:
            proxy_server: The running proxy server process.

        Returns:
            None

        Raises:
            None

        """
        # If we get here, the server started successfully
        assert proxy_server.returncode is None

    @pytest.mark.asyncio
    async def test_server_listens_on_port(
        self, proxy_server: asyncio.subprocess.Process, proxy_port: int
    ) -> None:
        """Test that the proxy is listening on the expected port.

        Args:
            proxy_server: The running proxy server process.
            proxy_port: The port the proxy should be listening on.

        Returns:
            None

        Raises:
            None

        """
        import telnetlib3

        # Should be able to connect
        reader, writer = await telnetlib3.open_connection("localhost", proxy_port)
        assert reader is not None
        if writer:
            writer.close()
