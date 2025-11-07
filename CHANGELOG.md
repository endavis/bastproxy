# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added
- Comprehensive testing infrastructure with pytest
- Type checking with mypy
- Enhanced linting with Ruff (27+ rule sets)
- GitHub Actions CI/CD pipeline (test, lint, release workflows)
- Pre-commit hooks for automatic code quality checks
- EditorConfig for consistent editor settings
- Comprehensive CONTRIBUTING.md with development guidelines
- Expanded README.md with installation and usage documentation
- LICENSE file (MIT)
- py.typed markers for PEP 561 compliance
- Code coverage reporting with Codecov integration

### Changed
- Updated package metadata in pyproject.toml with complete information
- Improved project description to mention Python 3.12+ requirement
- Added dev dependencies for testing and code quality tools

### Fixed
- (Pending) Dependency loading issue
- (Pending) Commands not being removed on plugin reload

## [2.0.0] - Previous Release

### Major Features
- Complete rewrite for Python 3.12+
- Asynchronous architecture using asyncio
- Plugin system with hot-reload capabilities
- Event-driven architecture
- API framework for plugin communication
- Comprehensive telnet protocol support (GMCP, MSDP, MSSP, MCCP, MXP)
- Multiple client connection support
- Data tracking and monitoring system

### Core Plugins
- Command parsing and execution system
- Event registration and notification
- Trigger system for pattern matching
- Client connection management
- Proxy configuration
- Logging infrastructure
- Settings management
- Color handling (ANSI/Xterm)
- SQL database base class
- Command queue management
- Timer functionality
- Fuzzy string matching
- Error handling

---

## Release Types

- **Major**: Incompatible API changes
- **Minor**: Backwards-compatible functionality additions
- **Patch**: Backwards-compatible bug fixes

## Categories

- **Added**: New features
- **Changed**: Changes in existing functionality
- **Deprecated**: Soon-to-be removed features
- **Removed**: Removed features
- **Fixed**: Bug fixes
- **Security**: Vulnerability fixes
