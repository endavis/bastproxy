# BastProxy

[![Tests](https://github.com/endavis/bastproxy-py3/actions/workflows/test.yml/badge.svg)](https://github.com/endavis/bastproxy-py3/actions/workflows/test.yml)
[![Lint](https://github.com/endavis/bastproxy-py3/actions/workflows/lint.yml/badge.svg)](https://github.com/endavis/bastproxy-py3/actions/workflows/lint.yml)
[![Python 3.12+](https://img.shields.io/badge/python-3.12+-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

A powerful, extensible MUD (Multi-User Dungeon) proxy built with Python 3.12+ and asyncio. BastProxy sits between your MUD client and MUD server, providing features like triggers, aliases, logging, and a rich plugin system.

## Features

- **Asynchronous Architecture**: Built on Python's asyncio for efficient handling of multiple connections
- **Plugin System**: Highly modular with hot-reload capabilities
- **Telnet Protocol Support**: GMCP, MSDP, MSSP, MCCP, MXP, and more
- **Event-Driven**: Comprehensive event system for plugin interaction
- **API Framework**: Centralized API registry for plugin communication
- **Command System**: Flexible command parsing and execution
- **Trigger System**: Pattern matching on MUD output
- **Multiple Clients**: Support for multiple simultaneous client connections
- **Data Tracking**: Comprehensive tracking of data flows and modifications

## Quick Start

### Prerequisites

- Python 3.12 or newer
- pip (Python package installer)

### Installation

1. **Clone the repository**:
   ```bash
   git clone https://github.com/endavis/bastproxy-py3.git
   cd bastproxy-py3
   ```

2. **Install dependencies**:
   ```bash
   pip install -r requirements.txt
   ```
   
   Or for development:
   ```bash
   pip install -e ".[dev]"
   ```

### Running BastProxy

**Basic usage**:
```bash
python mudproxy.py
```

**With options**:
```bash
python mudproxy.py --port 9999 --IPv4-address localhost
```

**Command-line options**:
- `--port` or `-p`: Port to listen on (default: 9999)
- `--IPv4-address`: IP address to bind to (default: localhost)
- `--profile` or `-pf`: Enable code profiling

### Connecting

1. Start BastProxy with `python mudproxy.py`
2. Connect your MUD client to `localhost:9999`
3. BastProxy will prompt you to configure your MUD connection
4. Once configured, BastProxy connects to your MUD server

## Configuration

Configuration files are stored in `data/plugins/`. Each plugin maintains its own configuration.

### Core Plugins

- **commands**: Command parsing and execution
- **events**: Event registration and notification
- **triggers**: Pattern matching and text substitution
- **clients**: Client connection management
- **proxy**: Core proxy settings
- **log**: Logging infrastructure
- **settings**: Plugin settings management
- **colors**: ANSI/Xterm color handling

## Plugin Development

BastProxy uses a powerful plugin system. Here's a minimal plugin example:

### Plugin Structure

```python
# plugins/your_plugin/__init__.py
PLUGIN_NAME = 'Your Plugin'
PLUGIN_PURPOSE = 'Does something useful'
PLUGIN_AUTHOR = 'Your Name'
PLUGIN_VERSION = 1

# plugins/your_plugin/plugin/_yourplugin.py
from plugins._baseplugin import BasePlugin
from libs.api import AddAPI

class YourPlugin(BasePlugin):
    """Your plugin implementation."""
    
    @AddAPI('your.api.function', description='Your API function')
    def _api_your_function(self, data: str) -> str:
        """Process data."""
        return f"Processed: {data}"
```

See [CONTRIBUTING.md](CONTRIBUTING.md) for detailed plugin development guidelines.

## Development

### Setup Development Environment

```bash
# Install with development dependencies
pip install -e ".[dev]"

# Install pre-commit hooks
pre-commit install
```

### Running Tests

```bash
# Run all tests
pytest

# Run with coverage
pytest --cov=libs --cov=plugins --cov-report=html

# Run specific test
pytest tests/libs/test_persistentdict.py
```

### Code Quality

```bash
# Lint code
ruff check .

# Format code
black .

# Type checking
mypy mudproxy.py libs/ plugins/
```

## Project Structure

```
bastproxy-py3/
├── mudproxy.py          # Main entry point
├── libs/                # Core libraries
│   ├── api/            # API framework
│   ├── net/            # Network handling
│   ├── plugins/        # Plugin loading system
│   ├── records/        # Data tracking
│   └── tracking/       # Attribute monitoring
├── plugins/            # Plugin directory
│   ├── core/          # Core plugins
│   ├── debug/         # Debug plugins
│   └── _baseplugin/   # Base plugin class
├── tests/             # Test suite
└── data/              # Runtime data
    ├── logs/          # Log files
    └── plugins/       # Plugin data
```

## Contributing

Contributions are welcome! Please read [CONTRIBUTING.md](CONTRIBUTING.md) for details on our code of conduct and the process for submitting pull requests.

### Quick Contribution Guide

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/amazing-feature`)
3. Make your changes following our [coding standards](CONTRIBUTING.md#coding-standards)
4. Write tests for your changes
5. Ensure all tests pass (`pytest`)
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

- **Issues**: [GitHub Issues](https://github.com/endavis/bastproxy-py3/issues)
- **Documentation**: [Wiki](https://github.com/endavis/bastproxy-py3/wiki)

## Acknowledgments

- Original BastProxy concept and design by Bast
- Community contributors and testers
- The MUD community for continued support
