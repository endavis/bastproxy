# Contributing to BastProxy

Thank you for your interest in contributing to BastProxy! This document provides guidelines and instructions for contributing to the project.

## Table of Contents

- [Code of Conduct](#code-of-conduct)
- [Getting Started](#getting-started)
- [Development Setup](#development-setup)
- [Coding Standards](#coding-standards)
- [Testing](#testing)
- [Submitting Changes](#submitting-changes)
- [Plugin Development](#plugin-development)

## Code of Conduct

- Be respectful and inclusive
- Focus on constructive feedback
- Help maintain a positive community

## Getting Started

1. **Fork the repository** on GitHub
2. **Clone your fork** locally:
   ```bash
   git clone https://github.com/YOUR-USERNAME/bastproxy-py3.git
   cd bastproxy-py3
   ```
3. **Add the upstream remote**:
   ```bash
   git remote add upstream https://github.com/endavis/bastproxy-py3.git
   ```

## Development Setup

### Prerequisites

- Python 3.12 or newer
- Git

### Installation

1. **Create a virtual environment**:
   ```bash
   python -m venv venv
   source venv/bin/activate  # On Windows: venv\Scripts\activate
   ```

2. **Install dependencies**:
   ```bash
   pip install -e ".[dev]"
   ```

3. **Install pre-commit hooks**:
   ```bash
   pre-commit install
   ```

### Running the Proxy

```bash
python mudproxy.py
```

Or with options:
```bash
python mudproxy.py --port 9999 --IPv4-address localhost
```

## Coding Standards

### Python Style

- **Python Version**: Python 3.12+
- **Style Guide**: Google Python Style Guide
- **Line Length**: 88 characters
- **Docstrings**: Google format, no more than 88 characters per line
- **Type Hints**: Required for all parameters, variables, and return values

### Documentation

- All modules must have module-level docstrings
- All public classes and functions must have docstrings
- Docstrings should include:
  - Summary (one line, < 75 characters)
  - Detailed description
  - Args section
  - Returns section
  - Raises section (if applicable)

Example:
```python
def process_data(data: dict[str, Any], validate: bool = True) -> list[str]:
    """Process input data and return formatted results.

    This function takes a dictionary of data, optionally validates it,
    and returns a list of formatted string representations.

    Args:
        data: Dictionary containing the data to process.
        validate: Whether to validate data before processing.

    Returns:
        List of formatted strings representing the processed data.

    Raises:
        ValueError: If validation fails and validate is True.

    """
    # Implementation
```

### Code Quality Tools

Run these commands before committing:

```bash
# Format code
black .
ruff check . --fix

# Type checking
./scripts/typecheck.sh

# Run tests
pytest

# Run all checks
pre-commit run --all-files
```

## Testing

### Running Tests

```bash
# Run all tests
pytest

# Run with coverage
pytest --cov=libs --cov=plugins --cov-report=html

# Run specific test file
pytest tests/libs/test_persistentdict.py

# Run tests matching a pattern
pytest -k "test_persistence"
```

### Writing Tests

- Place tests in the `tests/` directory
- Mirror the structure of the code being tested
- Use descriptive test names: `test_<what>_<condition>_<expected_result>`
- Use pytest fixtures for common setup
- Aim for high code coverage

Example:
```python
def test_queue_maintains_fifo_order():
    """Test that queue maintains FIFO order."""
    q = Queue()

    q.enqueue("first")
    q.enqueue("second")
    q.enqueue("third")

    assert q.dequeue() == "first"
    assert q.dequeue() == "second"
    assert q.dequeue() == "third"
```

## Submitting Changes

### Creating a Pull Request

1. **Create a feature branch**:
   ```bash
   git checkout -b feature/your-feature-name
   ```

2. **Make your changes** following the coding standards

3. **Commit your changes**:
   ```bash
   git add .
   git commit -m "Add feature: description"
   ```

   Commit message format:
   - First line: Brief summary (< 50 characters)
   - Blank line
   - Detailed description (wrap at 72 characters)

4. **Push to your fork**:
   ```bash
   git push origin feature/your-feature-name
   ```

5. **Create a Pull Request** on GitHub

### Pull Request Checklist

- [ ] Code follows the project's style guidelines
- [ ] Self-review of code completed
- [ ] Comments added for complex logic
- [ ] Documentation updated (if needed)
- [ ] Tests added/updated
- [ ] All tests pass
- [ ] No new warnings from linters
- [ ] PR description explains the changes

### Commit Message Guidelines

**Format:**
```
<type>: <subject>

<body>

<footer>
```

**Types:**
- `feat`: New feature
- `fix`: Bug fix
- `docs`: Documentation changes
- `style`: Code style changes (formatting)
- `refactor`: Code refactoring
- `test`: Adding/updating tests
- `chore`: Maintenance tasks

**Example:**
```
feat: Add fuzzy matching for command names

Implements fuzzy string matching using rapidfuzz library to allow
partial command name matching. This improves user experience by
accepting commands with minor typos.

Closes #123
```

## Plugin Development

### Plugin Structure

```
plugins/your_plugin/
├── __init__.py          # Plugin metadata
├── plugin/              # Plugin implementation
│   ├── __init__.py
│   └── _yourplugin.py
└── libs/                # Helper libraries (optional)
    └── _utils.py
```

### Plugin Template

```python
# plugins/your_plugin/__init__.py

PLUGIN_NAME = 'Your Plugin Name'
PLUGIN_PURPOSE = 'Brief description'
PLUGIN_AUTHOR = 'Your Name'
PLUGIN_VERSION = 1

PLUGIN_REQUIRED = False  # True for core plugins
```

### Plugin Class

```python
from plugins._baseplugin import BasePlugin
from libs.api import AddAPI

class YourPlugin(BasePlugin):
    """Your plugin implementation."""

    def __init__(self, plugin_id, plugin_info):
        """Initialize the plugin."""
        super().__init__(plugin_id, plugin_info)

    @AddAPI('your.api.function', description='API description')
    def _api_your_function(self, param: str) -> str:
        """Your API function."""
        return f"Result: {param}"
```

### Plugin Best Practices

- Use the API system for inter-plugin communication
- Register event handlers for plugin interaction
- Keep plugin data in the designated data directory
- Document all public APIs
- Handle errors gracefully
- Clean up resources in plugin unload

### API Naming Conventions

When adding new APIs with `@AddAPI`, follow these naming patterns:

1. **Verb-First for Actions** (most common):
   - Pattern: `<verb>.<noun>[.<modifier>]`
   - Examples: `add.timer`, `get.plugin.info`, `remove.timer`, `set.reload`
   - Verbs: `add`, `get`, `remove`, `set`, `update`, `change`

2. **Noun-First for Resource Operations**:
   - Pattern: `<resource>.<verb>[.<modifier>]`
   - Examples: `client.add`, `timer.remove`, `plugin.get`
   - Use when grouping APIs by resource type

3. **Domain-First for Utilities/Converters**:
   - Pattern: `<domain>.<operation>`
   - Examples: `colorcode.to.html`, `format.time`, `convert.seconds.to.dhms`
   - Use for conversion, formatting, and utility functions

4. **Boolean Checks**:
   - Pattern: `is.<condition>` or `<resource>.is.<condition>`
   - Examples: `is.plugin.loaded`, `timer.is.enabled`
   - Avoid: `has.*`, `does.*`, `can.*` (use `is.*` consistently)

5. **Dot Notation**:
   - Use dots to create hierarchies: `plugin.dependency.add`
   - Keep API names concise but descriptive
   - Maximum 3-4 levels deep

**Examples:**
```python
@AddAPI('timer.add', description='add a timer')
@AddAPI('is.timer.exists', description='check if a timer exists')
@AddAPI('colorcode.to.ansicode', description='convert color codes')
@AddAPI('get.plugin.info', description='get plugin information')
```

## Questions?

- Open an issue for bugs or feature requests
- Check existing issues before creating new ones
- Be clear and detailed in your descriptions

## License

By contributing, you agree that your contributions will be licensed under the MIT License.

---

Thank you for contributing to BastProxy! 🎉
