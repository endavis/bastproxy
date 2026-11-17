# BastProxy

[![CI](https://github.com/endavis/bastproxy/actions/workflows/ci.yml/badge.svg)](https://github.com/endavis/bastproxy/actions/workflows/ci.yml)
[![Python 3.12+](https://img.shields.io/badge/python-3.12+-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

A powerful, extensible MUD (Multi-User Dungeon) proxy built with Python 3.12+ and asyncio. BastProxy sits between your MUD client and MUD server, providing features like triggers, aliases, logging, and a rich plugin system.

## Features

- **Asynchronous Architecture**: Built on Python's asyncio for efficient handling of multiple connections
- **Plugin System**: Highly modular with hot-reload capabilities
- **Telnet Protocol Support (planned)**: GMCP, MSDP, MSSP, MCCP and MXP are not handled yet. The design is in [ADR-0001](docs/decisions/0001-terminate-mud-telnet-protocols-at-the-proxy.md) (Proposed), and the work is tracked in [#58](https://github.com/endavis/bastproxy/issues/58) (MCCP), [#59](https://github.com/endavis/bastproxy/issues/59) (GMCP and MSDP), [#60](https://github.com/endavis/bastproxy/issues/60) (MSSP) and [#61](https://github.com/endavis/bastproxy/issues/61) (MXP)
- **Event-Driven**: Comprehensive event system for plugin interaction
- **API Framework**: Centralized API registry for plugin communication
- **Command System**: Flexible command parsing and execution
- **Trigger System**: Pattern matching on MUD output
- **Multiple Clients**: Support for multiple simultaneous client connections
- **Data Tracking**: Comprehensive tracking of data flows and modifications

## Quick Start

### Prerequisites

- Python 3.12 or newer
- uv (for dependency management) or pip

### Installation

1. **Clone the repository**:
   ```bash
   git clone https://github.com/endavis/bastproxy.git
   cd bastproxy
   ```

2. **Install dependencies**:
   ```bash
   uv sync --all-extras
   ```

   Or for development:
   ```bash
   pip install -e ".[dev]"
   ```

### Running BastProxy

`BASTPROXY_HOME` must point at an existing, writable directory. BastProxy keeps its data, plugin settings, user plugins and logs under it, and importing `bastproxy` fails without it. `.envrc` defaults it to `~/bastproxy`.

**Basic usage**:
```bash
uv run bastproxy
```

**With options**:
```bash
uv run bastproxy --port 9999 --IPv4-address localhost
```

**Command-line options**:
- `--port` or `-p`: Port to listen on (default: 9999)
- `--IPv4-address`: IP address to bind to (default: localhost)
- `--profile` or `-pf`: Enable code profiling
- `--quiet` or `-q`: Suppress console output (logs are still written to file)

### Connecting

1. Start BastProxy with `uv run bastproxy`
2. Connect your MUD client to `localhost:9999`
3. BastProxy will prompt you to configure your MUD connection
4. Once configured, BastProxy connects to your MUD server
5. Run `#bp.core.help.topic` to see the in-proxy guides

## Configuration

Configuration files are stored in `$BASTPROXY_HOME/data/plugins/`. Each plugin maintains its own configuration.

### Core Plugins

- **clients**: Manage clients
- **colors**: Ansi/Xterm color functions
- **commands**: Parse and handle commands
- **errors**: Show and manage errors
- **events**: Handle events
- **fuzzy**: Do fuzzy matching
- **help**: Guides to using the proxy (#bp.core.help.topic)
- **log**: Handles changing and testing of logging configuration
- **mudcmds**: Queue commands to the mud
- **pluginm**: Manage plugins
- **proxy**: Control the proxy
- **settings**: Plugin to handle settings
- **sqldb**: Hold the SQL DB baseclass
- **ssc**: Class to save settings that should not stay in memory
- **timers**: Handle timers
- **triggers**: Handle triggers
- **utils**: Utility functions
- **watch**: Watch for specific commands from clients

## Plugin Development

User plugins go in `$BASTPROXY_HOME/plugins/<package>/<plugin>`; see the [plugin system docs](docs/claude/plugin_system.md#user-plugins).

The [Plugin Developer Guide](docs/plugin-developer-guide.md) covers the plugin file structure, metadata, the `Plugin` export, reloading, hooks and events, commands and triggers.

## Development

### Setup Development Environment

```bash
# Install with development dependencies
uv sync --all-extras

# Or through doit
uv run doit install_dev

# Install pre-commit hooks
uv run doit pre_commit_install
```

### Running Tests

```bash
# Run all tests
uv run doit test

# Run with coverage
uv run doit coverage

# Run a specific test file
uv run pytest tests/libs/test_persistentdict.py
```

### Code Quality

```bash
# Format code
uv run doit format

# Lint code
uv run doit lint

# Type checking
uv run doit type_check

# Run all checks
uv run doit check
```

If `~/bastproxy` does not exist, point `BASTPROXY_HOME` at a directory that does, for example `BASTPROXY_HOME=$PWD uv run doit check`.

## Project Structure

```
bastproxy/
├── src/bastproxy/       # The package (entry point: bastproxy:main)
│   ├── libs/           # Core libraries
│   │   ├── api/        # API framework
│   │   ├── asynch/     # Async helpers
│   │   ├── info/       # Info helpers
│   │   ├── net/        # Network handling
│   │   ├── plugins/    # Plugin loading system
│   │   └── records/    # Data tracking
│   └── plugins/        # Plugin directory
│       ├── _baseplugin/  # Base plugin class
│       ├── core/       # Core plugins
│       ├── debug/      # Debug plugins
│       └── test/       # Test plugins
├── tests/              # Test suite
│   ├── libs/           # Tests for libs/
│   └── plugins/        # Tests for plugins/
└── docs/               # Documentation
```

Runtime data is not stored in the repository. It lives under `$BASTPROXY_HOME`: `data/` (plugin data and logs) and `plugins/` (user plugins).

## Contributing

Contributions are welcome! Please read [CONTRIBUTING.md](CONTRIBUTING.md) for details on our code of conduct and the process for submitting pull requests. The full issue, branch, commit and PR workflow is in [.github/CONTRIBUTING.md](.github/CONTRIBUTING.md).

### Quick Contribution Guide

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/amazing-feature`)
3. Make your changes following our [coding standards](CONTRIBUTING.md#coding-standards)
4. Write tests for your changes
5. Ensure all checks pass (`uv run doit check`)
6. Commit your changes (`git commit -m 'Add amazing feature'`)
7. Push to the branch (`git push origin feature/amazing-feature`)
8. Open a Pull Request

## Credits

The networking code is based on:
- [telnetlib3](https://github.com/jquast/telnetlib3) - Telnet protocol implementation
- [akrios_frontend](https://github.com/bdubyapee/akrios-frontend) - MUD client frontend

## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

## Support

- **Issues**: [GitHub Issues](https://github.com/endavis/bastproxy/issues)
- **Documentation**: [docs/](docs/index.md)

## Acknowledgments

- Original BastProxy concept and design by Bast
- Community contributors and testers
- The MUD community for continued support
