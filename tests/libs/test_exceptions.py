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

from bastproxy.libs.exceptions import (
    APIError,
    APIInvocationError,
    APINotFoundError,
    APIRegistrationError,
    BastProxyError,
    ConfigurationError,
    ConnectionError,
    InvalidSettingError,
    MissingSettingError,
    NetworkError,
    PluginDependencyError,
    PluginError,
    PluginExecutionError,
    PluginLoadError,
    PluginValidationError,
    RecordError,
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
        """Test that PluginError inherits from BastProxyError."""
        assert issubclass(PluginError, BastProxyError)

    def test_plugin_load_error(self) -> None:
        """Test PluginLoadError exception."""
        error = PluginLoadError("Failed to load plugin")

        assert isinstance(error, PluginError)
        assert isinstance(error, BastProxyError)
        assert str(error) == "Failed to load plugin"

    def test_plugin_validation_error(self) -> None:
        """Test PluginValidationError exception."""
        error = PluginValidationError("Plugin validation failed")

        assert isinstance(error, PluginError)
        assert str(error) == "Plugin validation failed"

    def test_plugin_execution_error(self) -> None:
        """Test PluginExecutionError exception."""
        error = PluginExecutionError("Plugin execution failed")

        assert isinstance(error, PluginError)
        assert str(error) == "Plugin execution failed"

    def test_plugin_dependency_error(self) -> None:
        """Test PluginDependencyError exception."""
        error = PluginDependencyError("Dependency not found")

        assert isinstance(error, PluginError)
        assert str(error) == "Dependency not found"

    def test_catch_plugin_exception_with_load_error(self) -> None:
        """Test catching PluginLoadError with base PluginError."""
        with pytest.raises(PluginError):
            raise_plugin_load_error()

    def test_catch_plugin_exception_with_validation_error(self) -> None:
        """Test catching PluginValidationError with base PluginError."""
        with pytest.raises(PluginError):
            raise_plugin_validation_error()

    def test_plugin_exception_hierarchy(self) -> None:
        """Test that all plugin exceptions inherit correctly."""
        assert issubclass(PluginLoadError, PluginError)
        assert issubclass(PluginValidationError, PluginError)
        assert issubclass(PluginExecutionError, PluginError)
        assert issubclass(PluginDependencyError, PluginError)


class TestAPIExceptions:
    """Test API-related exceptions."""

    def test_api_exception_inherits_from_bastproxy_error(self) -> None:
        """Test that APIError inherits from BastProxyError."""
        assert issubclass(APIError, BastProxyError)

    def test_api_registration_error(self) -> None:
        """Test APIRegistrationError exception."""
        error = APIRegistrationError("API registration failed")

        assert isinstance(error, APIError)
        assert isinstance(error, BastProxyError)
        assert str(error) == "API registration failed"

    def test_api_not_found_error(self) -> None:
        """Test APINotFoundError exception."""
        error = APINotFoundError("API not found")

        assert isinstance(error, APIError)
        assert isinstance(error, BastProxyError)
        assert isinstance(error, AttributeError)
        assert str(error) == "API not found"

    def test_api_invocation_error(self) -> None:
        """Test APIInvocationError exception."""
        error = APIInvocationError("API invocation failed")

        assert isinstance(error, APIError)
        assert str(error) == "API invocation failed"

    def test_catch_api_exception_with_registration_error(self) -> None:
        """Test catching APIRegistrationError with base APIError."""
        with pytest.raises(APIError):
            raise_api_registration_error()

    def test_catch_api_exception_with_not_found_error(self) -> None:
        """Test catching APINotFoundError with base APIError."""
        with pytest.raises(APIError):
            raise_api_not_found_error()

    def test_api_exception_hierarchy(self) -> None:
        """Test that all API exceptions inherit correctly."""
        assert issubclass(APIRegistrationError, APIError)
        assert issubclass(APINotFoundError, APIError)
        assert issubclass(APIInvocationError, APIError)


class TestNetworkExceptions:
    """Test network-related exceptions."""

    def test_network_exception_inherits_from_bastproxy_error(self) -> None:
        """Test that NetworkError inherits from BastProxyError."""
        assert issubclass(NetworkError, BastProxyError)

    def test_connection_error(self) -> None:
        """Test ConnectionError exception."""
        error = ConnectionError("Connection failed")

        assert isinstance(error, NetworkError)
        assert isinstance(error, BastProxyError)
        assert str(error) == "Connection failed"

    def test_telnet_protocol_error(self) -> None:
        """Test TelnetProtocolError exception."""
        error = TelnetProtocolError("Telnet protocol error")

        assert isinstance(error, NetworkError)
        assert str(error) == "Telnet protocol error"

    def test_catch_network_exception_with_connection_error(self) -> None:
        """Test catching ConnectionError with base NetworkError."""
        with pytest.raises(NetworkError):
            raise_connection_error()

    def test_catch_network_exception_with_protocol_error(self) -> None:
        """Test catching TelnetProtocolError with base NetworkError."""
        with pytest.raises(NetworkError):
            raise_telnet_protocol_error()

    def test_network_exception_hierarchy(self) -> None:
        """Test that all network exceptions inherit correctly."""
        assert issubclass(ConnectionError, NetworkError)
        assert issubclass(TelnetProtocolError, NetworkError)


class TestConfigurationExceptions:
    """Test configuration-related exceptions."""

    def test_configuration_exception_inherits_from_bastproxy_error(self) -> None:
        """Test that ConfigurationError inherits from BastProxyError."""
        assert issubclass(ConfigurationError, BastProxyError)

    def test_invalid_setting_error(self) -> None:
        """Test InvalidSettingError exception."""
        error = InvalidSettingError("Invalid setting value")

        assert isinstance(error, ConfigurationError)
        assert isinstance(error, BastProxyError)
        assert str(error) == "Invalid setting value"

    def test_missing_setting_error(self) -> None:
        """Test MissingSettingError exception."""
        error = MissingSettingError("Required setting missing")

        assert isinstance(error, ConfigurationError)
        assert str(error) == "Required setting missing"

    def test_catch_config_exception_with_invalid_setting(self) -> None:
        """Test catching InvalidSettingError with ConfigurationError."""
        with pytest.raises(ConfigurationError):
            raise_invalid_setting_error()

    def test_catch_config_exception_with_missing_setting(self) -> None:
        """Test catching MissingSettingError with ConfigurationError."""
        with pytest.raises(ConfigurationError):
            raise_missing_setting_error()

    def test_configuration_exception_hierarchy(self) -> None:
        """Test that all configuration exceptions inherit correctly."""
        assert issubclass(InvalidSettingError, ConfigurationError)
        assert issubclass(MissingSettingError, ConfigurationError)


class TestRecordExceptions:
    """Test record processing exceptions."""

    def test_record_exception_inherits_from_bastproxy_error(self) -> None:
        """Test that RecordError inherits from BastProxyError."""
        assert issubclass(RecordError, BastProxyError)

    def test_record_validation_error(self) -> None:
        """Test RecordValidationError exception."""
        error = RecordValidationError("Record validation failed")

        assert isinstance(error, RecordError)
        assert isinstance(error, BastProxyError)
        assert str(error) == "Record validation failed"

    def test_record_serialization_error(self) -> None:
        """Test RecordSerializationError exception."""
        error = RecordSerializationError("Serialization failed")

        assert isinstance(error, RecordError)
        assert str(error) == "Serialization failed"

    def test_catch_record_exception_with_validation_error(self) -> None:
        """Test catching RecordValidationError with base RecordError."""
        with pytest.raises(RecordError):
            raise_record_validation_error()

    def test_catch_record_exception_with_serialization_error(self) -> None:
        """Test catching RecordSerializationError with base RecordError."""
        with pytest.raises(RecordError):
            raise_record_serialization_error()

    def test_record_exception_hierarchy(self) -> None:
        """Test that all record exceptions inherit correctly."""
        assert issubclass(RecordValidationError, RecordError)
        assert issubclass(RecordSerializationError, RecordError)


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
        # PluginLoadError is a PluginError, not an APIError
        with pytest.raises(PluginError):
            raise_plugin_load_error()

    def test_all_base_exceptions_inherit_from_bastproxy_error(self) -> None:
        """Test that all base exception classes inherit from BastProxyError."""
        base_exceptions = [
            PluginError,
            APIError,
            NetworkError,
            ConfigurationError,
            RecordError,
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
        assert isinstance(error, PluginError)
        assert isinstance(error, BastProxyError)
        assert isinstance(error, Exception)

        # Not instances of sibling classes
        assert not isinstance(error, APIError)
        assert not isinstance(error, NetworkError)


class TestNamingRenames:
    """Tests for the N818 and N802 renames (#6)."""

    def test_new_exception_names_exist_and_old_are_gone(self) -> None:
        """The *Error names exist and the *Exception names are removed."""
        from bastproxy.libs import exceptions

        for new, old in (
            ("PluginError", "PluginException"),
            ("APIError", "APIException"),
            ("NetworkError", "NetworkException"),
            ("ConfigurationError", "ConfigurationException"),
            ("RecordError", "RecordException"),
        ):
            assert hasattr(exceptions, new)
            assert not hasattr(exceptions, old)

    def test_format_time_functions_importable(self) -> None:
        """The snake_case log time formatters are importable from the log plugin."""
        from bastproxy.plugins.core.log import format_time_rfc3339, format_time_rfc3339_utc

        assert callable(format_time_rfc3339)
        assert callable(format_time_rfc3339_utc)
