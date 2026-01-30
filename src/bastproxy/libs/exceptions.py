"""Custom exception hierarchy for BastProxy.

This module provides a structured hierarchy of exceptions used throughout
BastProxy. All custom exceptions inherit from BastProxyError, making it easy
to catch all proxy-related exceptions while still allowing fine-grained error
handling for specific cases.

Key Components:
    - BastProxyError: Base exception for all BastProxy errors.
    - PluginException: Plugin-related errors (loading, validation, execution).
    - APIException: API registration and invocation errors.
    - NetworkException: Network communication errors (client/server).
    - ConfigurationException: Configuration and settings errors.
    - RecordException: Data record processing errors.

Features:
    - Hierarchical structure for granular error handling.
    - Consistent error messages across the application.
    - Type-safe exception handling with specific exception classes.

Usage:
    - Raise specific exceptions for different error conditions.
    - Catch BastProxyError to handle all proxy errors.
    - Use specific exception types for targeted error handling.

Classes:
    - `BastProxyError`: Base exception class for all BastProxy errors.
    - `PluginException`: Exception for plugin-related errors.
    - `PluginLoadError`: Exception for plugin loading failures.
    - `PluginValidationError`: Exception for plugin validation failures.
    - `PluginExecutionError`: Exception for plugin execution failures.
    - `PluginDependencyError`: Exception for plugin dependency issues.
    - `APIException`: Exception for API-related errors.
    - `APIRegistrationError`: Exception for API registration failures.
    - `APINotFoundError`: Exception when API is not found.
    - `APIInvocationError`: Exception for API invocation failures.
    - `NetworkException`: Exception for network-related errors.
    - `ConnectionError`: Exception for connection failures.
    - `TelnetProtocolError`: Exception for Telnet protocol errors.
    - `ConfigurationException`: Exception for configuration errors.
    - `InvalidSettingError`: Exception for invalid setting values.
    - `MissingSettingError`: Exception for missing required settings.
    - `RecordException`: Exception for record processing errors.
    - `RecordValidationError`: Exception for record validation failures.
    - `RecordSerializationError`: Exception for serialization failures.

"""


class BastProxyError(Exception):
    """Base exception class for all BastProxy errors.

    All custom exceptions in BastProxy should inherit from this class to
    provide a consistent exception hierarchy and enable catching all
    proxy-related errors with a single except clause.

    """


# ============================================================================
# Plugin Exceptions
# ============================================================================


class PluginException(BastProxyError):
    """Base exception for all plugin-related errors.

    This exception is the parent class for all plugin-specific errors
    including loading, validation, execution, and dependency issues.

    """


class PluginLoadError(PluginException):
    """Exception raised when a plugin fails to load.

    This exception is raised when a plugin cannot be loaded due to import
    errors, missing dependencies, or other initialization failures.

    """


class PluginValidationError(PluginException):
    """Exception raised when a plugin fails validation.

    This exception is raised when a plugin does not meet the required
    structure, is missing required attributes, or has invalid metadata.

    """


class PluginExecutionError(PluginException):
    """Exception raised when a plugin encounters an error during execution.

    This exception is raised when a plugin's method or API call fails during
    runtime, including errors in command handlers, event callbacks, or API
    implementations.

    """


class PluginDependencyError(PluginException):
    """Exception raised when plugin dependencies cannot be resolved.

    This exception is raised when a plugin requires another plugin that is
    not available, has an incompatible version, or creates a circular
    dependency.

    """


# ============================================================================
# API Exceptions
# ============================================================================


class APIException(BastProxyError):
    """Base exception for all API-related errors.

    This exception is the parent class for all API-specific errors including
    registration, lookup, and invocation failures.

    """


class APIRegistrationError(APIException):
    """Exception raised when API registration fails.

    This exception is raised when an API cannot be registered due to naming
    conflicts, invalid signatures, or decorator misuse.

    """


class APINotFoundError(APIException):
    """Exception raised when an API cannot be found.

    This exception is raised when attempting to invoke or look up an API
    that has not been registered or has been removed.

    """


class APIInvocationError(APIException):
    """Exception raised when an API call fails.

    This exception is raised when an API invocation fails due to invalid
    arguments, runtime errors, or other execution problems.

    """


# ============================================================================
# Network Exceptions
# ============================================================================


class NetworkException(BastProxyError):
    """Base exception for all network-related errors.

    This exception is the parent class for all network-specific errors
    including connection failures and protocol errors.

    """


class ConnectionError(NetworkException):
    """Exception raised when a network connection fails.

    This exception is raised when a client or server connection cannot be
    established, is lost unexpectedly, or times out.

    """


class TelnetProtocolError(NetworkException):
    """Exception raised when Telnet protocol handling fails.

    This exception is raised when parsing or handling Telnet protocol
    commands fails, including GMCP, MSDP, and other protocol extensions.

    """


# ============================================================================
# Configuration Exceptions
# ============================================================================


class ConfigurationException(BastProxyError):
    """Base exception for all configuration-related errors.

    This exception is the parent class for all configuration-specific errors
    including invalid settings and missing required configuration.

    """


class InvalidSettingError(ConfigurationException):
    """Exception raised when a setting has an invalid value.

    This exception is raised when a configuration setting is set to a value
    that does not meet validation requirements or has an incorrect type.

    """


class MissingSettingError(ConfigurationException):
    """Exception raised when a required setting is missing.

    This exception is raised when a required configuration setting is not
    provided or cannot be found in the configuration source.

    """


# ============================================================================
# Record Exceptions
# ============================================================================


class RecordException(BastProxyError):
    """Base exception for all record processing errors.

    This exception is the parent class for all record-specific errors
    including validation and serialization failures.

    """


class RecordValidationError(RecordException):
    """Exception raised when record validation fails.

    This exception is raised when a record does not meet validation
    requirements or has missing/invalid fields.

    """


class RecordSerializationError(RecordException):
    """Exception raised when record serialization/deserialization fails.

    This exception is raised when converting a record to or from a serialized
    format fails due to incompatible types or corrupted data.

    """
