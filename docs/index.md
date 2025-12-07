# bastproxy Documentation

Welcome to the documentation for bastproxy!

## Overview

bastproxy is a modern Python project template with comprehensive tooling for development, testing, documentation, and deployment.

## Quick Links

- [Installation Guide](installation.md)
- [User Guide](usage.md)
- [API Reference](api.md)
- [Contributing](https://github.com/endavis/bastproxy/blob/main/.github/CONTRIBUTING.md)

## Features

- ✅ **Modern Build System**: Uses `uv` for fast dependency management
- ✅ **Comprehensive Testing**: pytest with parallel execution (pytest-xdist)
- ✅ **Type Safety**: mypy with strict type checking in pre-commit hooks
- ✅ **Code Quality**: ruff for linting and formatting
- ✅ **Security Scanning**: bandit for security analysis
- ✅ **Spell Checking**: codespell for typo prevention
- ✅ **Documentation**: MkDocs with Material theme support
- ✅ **CI/CD**: GitHub Actions with safe release workflows
- ✅ **Pre-commit Hooks**: Automated code quality checks

## Quick Start

```python
from bastproxy import greet

# Simple greeting example
message = greet("Python")
print(message)  # Output: Hello, Python!
```

## Documentation Sections

### For Users

- **[Installation](installation.md)** - How to install the package
- **[Usage Guide](usage.md)** - How to use the package
- **[API Reference](api.md)** - Complete API documentation
- **[Migration Guide](migration.md)** - Move an existing project into this template

### For Contributors

- **[Contributing Guide](https://github.com/endavis/bastproxy/blob/main/.github/CONTRIBUTING.md)** - How to contribute
- **[Code of Conduct](https://github.com/endavis/bastproxy/blob/main/.github/CODE_OF_CONDUCT.md)** - Community guidelines
- **[Development Guide](https://github.com/endavis/bastproxy/blob/main/AGENTS.md)** - Development setup and standards

## Support

- **Issues:** [GitHub Issues](https://github.com/endavis/bastproxy/issues)
- **Discussions:** [GitHub Discussions](https://github.com/endavis/bastproxy/discussions)
- **Security:** See [SECURITY.md](https://github.com/endavis/bastproxy/blob/main/.github/SECURITY.md)

## License

This project is licensed under the MIT License - see the [LICENSE](https://github.com/endavis/bastproxy/blob/main/LICENSE) file for details.
