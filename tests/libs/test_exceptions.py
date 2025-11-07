"""Tests for the custom exception hierarchy.

This module tests the exception classes used throughout BastProxy including:
- Exception hierarchy and inheritance
- Exception instantiation and message handling
- Catching exceptions at different levels
- Exception type checking

Test Classes:
    - `TestBastProxyError`: Tests for the base exception class.
    - `TestPluginExceptions`: Tests for plugin-related exceptions.
    - `TestAPIExceptions`: Tests for API-related exceptions.
    - `TestNetworkExceptions`: Tests for network-related exceptions.
    - `TestConfigurationExceptions`: Tests for configuration exceptions.
    - `TestRecordExceptions`: Tests for record processing exceptions.
    - `TestExceptionHierarchy`: Tests for exception inheritance behavior.

"""

import pytest

from libs.exceptions import (
    APIException,
    APIInvocationError,
    APINotFoundError,
    APIRegistrationError,
    BastProxyError,
    ConfigurationException,
    ConnectionError,
    InvalidSettingError,
    MissingSettingError,
    NetworkException,
    PluginDependencyError,
    PluginException,
    PluginExecutionError,
    PluginLoadError,
    PluginValidationError,
    RecordException,
    RecordSerializationError,
    RecordValidationError,
    TelnetProtocolError,
)


def raise_bastproxy_error() -> None:
    """Helper function to raise BastProxyError."""
    msg = "Test error"
    raise BastProxyError(msg)


def raise_plugin_load_error() -> None:
    """Helper function to raise PluginLoadError."""
    msg = "Load failed"
    raise PluginLoadError(msg)


def raise_plugin_validation_error() -> None:
    """Helper function to raise PluginValidationError."""
    msg = "Validation failed"
    raise PluginValidationError(msg)


def raise_api_registration_error() -> None:
    """Helper function to raise APIRegistrationError."""
    msg = "Registration failed"
    raise APIRegistrationError(msg)


def raise_api_not_found_error() -> None:
    """Helper function to raise APINotFoundError."""
    msg = "Not found"
    raise APINotFoundError(msg)


def raise_connection_error() -> None:
    """Helper function to raise ConnectionError."""
    msg = "Connection failed"
    raise ConnectionError(msg)


def raise_telnet_protocol_error() -> None:
    """Helper function to raise TelnetProtocolError."""
    msg = "Protocol error"
    raise TelnetProtocolError(msg)


def raise_invalid_setting_error() -> None:
    """Helper function to raise InvalidSettingError."""
    msg = "Invalid value"
    raise InvalidSettingError(msg)


def raise_missing_setting_error() -> None:
    """Helper function to raise MissingSettingError."""
    msg = "Missing value"
    raise MissingSettingError(msg)


def raise_record_validation_error() -> None:
    """Helper function to raise RecordValidationError."""
    msg = "Validation failed"
    raise RecordValidationError(msg)


def raise_record_serialization_error() -> None:
    """Helper function to raise RecordSerializationError."""
    msg = "Serialization failed"
    raise RecordSerializationError(msg)


class TestBastProxyError:
    """Test the base exception class."""

    def test_bastproxy_error_instantiation(self) -> None:
        """Test that BastProxyError can be instantiated."""
        error = BastProxyError("Test error message")

        assert isinstance(error, Exception)
        assert str(error) == "Test error message"

    def test_bastproxy_error_without_message(self) -> None:
        """Test BastProxyError without a message."""
        error = BastProxyError()

        assert isinstance(error, Exception)

    def test_bastproxy_error_can_be_raised(self) -> None:
        """Test that BastProxyError can be raised."""
        with pytest.raises(BastProxyError) as exc_info:
            raise_bastproxy_error()

        assert str(exc_info.value) == "Test error"

    def test_bastproxy_error_is_exception(self) -> None:
        """Test that BastProxyError inherits from Exception."""
        assert issubclass(BastProxyError, Exception)


class TestPluginExceptions:
    """Test plugin-related exceptions."""

    def test_plugin_exception_inherits_from_bastproxy_error(self) -> None:
        """Test that PluginException inherits from BastProxyError."""
        assert issubclass(PluginException, BastProxyError)

    def test_plugin_load_error(self) -> None:
        """Test PluginLoadError exception."""
        error = PluginLoadError("Failed to load plugin")

        assert isinstance(error, PluginException)
        assert isinstance(error, BastProxyError)
        assert str(error) == "Failed to load plugin"

    def test_plugin_validation_error(self) -> None:
        """Test PluginValidationError exception."""
        error = PluginValidationError("Plugin validation failed")

        assert isinstance(error, PluginException)
        assert str(error) == "Plugin validation failed"

    def test_plugin_execution_error(self) -> None:
        """Test PluginExecutionError exception."""
        error = PluginExecutionError("Plugin execution failed")

        assert isinstance(error, PluginException)
        assert str(error) == "Plugin execution failed"

    def test_plugin_dependency_error(self) -> None:
        """Test PluginDependencyError exception."""
        error = PluginDependencyError("Dependency not found")

        assert isinstance(error, PluginException)
        assert str(error) == "Dependency not found"

    def test_catch_plugin_exception_with_load_error(self) -> None:
        """Test catching PluginLoadError with base PluginException."""
        with pytest.raises(PluginException):
            raise_plugin_load_error()

    def test_catch_plugin_exception_with_validation_error(self) -> None:
        """Test catching PluginValidationError with base PluginException."""
        with pytest.raises(PluginException):
            raise_plugin_validation_error()

    def test_plugin_exception_hierarchy(self) -> None:
        """Test that all plugin exceptions inherit correctly."""
        assert issubclass(PluginLoadError, PluginException)
        assert issubclass(PluginValidationError, PluginException)
        assert issubclass(PluginExecutionError, PluginException)
        assert issubclass(PluginDependencyError, PluginException)


class TestAPIExceptions:
    """Test API-related exceptions."""

    def test_api_exception_inherits_from_bastproxy_error(self) -> None:
        """Test that APIException inherits from BastProxyError."""
        assert issubclass(APIException, BastProxyError)

    def test_api_registration_error(self) -> None:
        """Test APIRegistrationError exception."""
        error = APIRegistrationError("API registration failed")

        assert isinstance(error, APIException)
        assert isinstance(error, BastProxyError)
        assert str(error) == "API registration failed"

    def test_api_not_found_error(self) -> None:
        """Test APINotFoundError exception."""
        error = APINotFoundError("API not found")

        assert isinstance(error, APIException)
        assert str(error) == "API not found"

    def test_api_invocation_error(self) -> None:
        """Test APIInvocationError exception."""
        error = APIInvocationError("API invocation failed")

        assert isinstance(error, APIException)
        assert str(error) == "API invocation failed"

    def test_catch_api_exception_with_registration_error(self) -> None:
        """Test catching APIRegistrationError with base APIException."""
        with pytest.raises(APIException):
            raise_api_registration_error()

    def test_catch_api_exception_with_not_found_error(self) -> None:
        """Test catching APINotFoundError with base APIException."""
        with pytest.raises(APIException):
            raise_api_not_found_error()

    def test_api_exception_hierarchy(self) -> None:
        """Test that all API exceptions inherit correctly."""
        assert issubclass(APIRegistrationError, APIException)
        assert issubclass(APINotFoundError, APIException)
        assert issubclass(APIInvocationError, APIException)


class TestNetworkExceptions:
    """Test network-related exceptions."""

    def test_network_exception_inherits_from_bastproxy_error(self) -> None:
        """Test that NetworkException inherits from BastProxyError."""
        assert issubclass(NetworkException, BastProxyError)

    def test_connection_error(self) -> None:
        """Test ConnectionError exception."""
        error = ConnectionError("Connection failed")

        assert isinstance(error, NetworkException)
        assert isinstance(error, BastProxyError)
        assert str(error) == "Connection failed"

    def test_telnet_protocol_error(self) -> None:
        """Test TelnetProtocolError exception."""
        error = TelnetProtocolError("Telnet protocol error")

        assert isinstance(error, NetworkException)
        assert str(error) == "Telnet protocol error"

    def test_catch_network_exception_with_connection_error(self) -> None:
        """Test catching ConnectionError with base NetworkException."""
        with pytest.raises(NetworkException):
            raise_connection_error()

    def test_catch_network_exception_with_protocol_error(self) -> None:
        """Test catching TelnetProtocolError with base NetworkException."""
        with pytest.raises(NetworkException):
            raise_telnet_protocol_error()

    def test_network_exception_hierarchy(self) -> None:
        """Test that all network exceptions inherit correctly."""
        assert issubclass(ConnectionError, NetworkException)
        assert issubclass(TelnetProtocolError, NetworkException)


class TestConfigurationExceptions:
    """Test configuration-related exceptions."""

    def test_configuration_exception_inherits_from_bastproxy_error(self) -> None:
        """Test that ConfigurationException inherits from BastProxyError."""
        assert issubclass(ConfigurationException, BastProxyError)

    def test_invalid_setting_error(self) -> None:
        """Test InvalidSettingError exception."""
        error = InvalidSettingError("Invalid setting value")

        assert isinstance(error, ConfigurationException)
        assert isinstance(error, BastProxyError)
        assert str(error) == "Invalid setting value"

    def test_missing_setting_error(self) -> None:
        """Test MissingSettingError exception."""
        error = MissingSettingError("Required setting missing")

        assert isinstance(error, ConfigurationException)
        assert str(error) == "Required setting missing"

    def test_catch_config_exception_with_invalid_setting(self) -> None:
        """Test catching InvalidSettingError with ConfigurationException."""
        with pytest.raises(ConfigurationException):
            raise_invalid_setting_error()

    def test_catch_config_exception_with_missing_setting(self) -> None:
        """Test catching MissingSettingError with ConfigurationException."""
        with pytest.raises(ConfigurationException):
            raise_missing_setting_error()

    def test_configuration_exception_hierarchy(self) -> None:
        """Test that all configuration exceptions inherit correctly."""
        assert issubclass(InvalidSettingError, ConfigurationException)
        assert issubclass(MissingSettingError, ConfigurationException)


class TestRecordExceptions:
    """Test record processing exceptions."""

    def test_record_exception_inherits_from_bastproxy_error(self) -> None:
        """Test that RecordException inherits from BastProxyError."""
        assert issubclass(RecordException, BastProxyError)

    def test_record_validation_error(self) -> None:
        """Test RecordValidationError exception."""
        error = RecordValidationError("Record validation failed")

        assert isinstance(error, RecordException)
        assert isinstance(error, BastProxyError)
        assert str(error) == "Record validation failed"

    def test_record_serialization_error(self) -> None:
        """Test RecordSerializationError exception."""
        error = RecordSerializationError("Serialization failed")

        assert isinstance(error, RecordException)
        assert str(error) == "Serialization failed"

    def test_catch_record_exception_with_validation_error(self) -> None:
        """Test catching RecordValidationError with base RecordException."""
        with pytest.raises(RecordException):
            raise_record_validation_error()

    def test_catch_record_exception_with_serialization_error(self) -> None:
        """Test catching RecordSerializationError with base RecordException."""
        with pytest.raises(RecordException):
            raise_record_serialization_error()

    def test_record_exception_hierarchy(self) -> None:
        """Test that all record exceptions inherit correctly."""
        assert issubclass(RecordValidationError, RecordException)
        assert issubclass(RecordSerializationError, RecordException)


class TestExceptionHierarchy:
    """Test exception hierarchy and catching behavior."""

    def test_catch_plugin_error_with_bastproxy_error(self) -> None:
        """Test that BastProxyError can catch plugin exceptions."""
        with pytest.raises(BastProxyError):
            raise_plugin_load_error()

    def test_catch_api_error_with_bastproxy_error(self) -> None:
        """Test that BastProxyError can catch API exceptions."""
        with pytest.raises(BastProxyError):
            raise_api_not_found_error()

    def test_catch_network_error_with_bastproxy_error(self) -> None:
        """Test that BastProxyError can catch network exceptions."""
        with pytest.raises(BastProxyError):
            raise_connection_error()

    def test_catch_config_error_with_bastproxy_error(self) -> None:
        """Test that BastProxyError can catch configuration exceptions."""
        with pytest.raises(BastProxyError):
            raise_invalid_setting_error()

    def test_catch_record_error_with_bastproxy_error(self) -> None:
        """Test that BastProxyError can catch record exceptions."""
        with pytest.raises(BastProxyError):
            raise_record_validation_error()

    def test_exception_message_preservation(self) -> None:
        """Test that exception messages are preserved through hierarchy."""
        msg = "Detailed error message"
        with pytest.raises(BastProxyError) as exc_info:
            raise PluginLoadError(msg)

        assert str(exc_info.value) == "Detailed error message"

    def test_specific_exception_not_caught_by_sibling(self) -> None:
        """Test that specific exceptions are not caught by sibling classes."""
        # PluginLoadError is a PluginException, not an APIException
        with pytest.raises(PluginException):
            raise_plugin_load_error()

    def test_all_base_exceptions_inherit_from_bastproxy_error(self) -> None:
        """Test that all base exception classes inherit from BastProxyError."""
        base_exceptions = [
            PluginException,
            APIException,
            NetworkException,
            ConfigurationException,
            RecordException,
        ]

        for exc_class in base_exceptions:
            assert issubclass(exc_class, BastProxyError)

    def test_exception_with_multiple_arguments(self) -> None:
        """Test exceptions with multiple arguments."""
        error = PluginLoadError("Plugin:", "test_plugin", "failed to load")

        assert isinstance(error, BastProxyError)
        # Multiple args are stored in args tuple
        assert len(error.args) == 3

    def test_exception_isinstance_checks(self) -> None:
        """Test isinstance checks work correctly across hierarchy."""
        error = PluginLoadError("Test")

        assert isinstance(error, PluginLoadError)
        assert isinstance(error, PluginException)
        assert isinstance(error, BastProxyError)
        assert isinstance(error, Exception)

        # Not instances of sibling classes
        assert not isinstance(error, APIException)
        assert not isinstance(error, NetworkException)
