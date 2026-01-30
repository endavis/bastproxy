# API Reference

Complete API documentation for bastproxy.

## Core Module

### `bastproxy.core`

Core functionality for the package.

#### Functions

##### `greet()`

```python
def greet(name: str = "World") -> str
```

Return a greeting message.

**Parameters:**
- `name` (str, optional): The name to greet. Defaults to "World".

**Returns:**
- `str`: A greeting message string.

**Example:**

```python
from bastproxy import greet

# Default greeting
message = greet()
print(message)  # Output: "Hello, World!"

# Custom greeting
message = greet("Python")
print(message)  # Output: "Hello, Python!"
```

**Doctests:**

```python
>>> greet()
'Hello, World!'
>>> greet("Python")
'Hello, Python!'
```

## Package Metadata

### `__version__`

```python
from bastproxy import __version__
```

The current version of the package as a string.

**Example:**

```python
import bastproxy
print(bastproxy.__version__)  # Derived from the git tag by hatch-vcs
```

## Module Structure

The package is organized as follows:

```
bastproxy/
├── __init__.py      # Package initialization, exports greet and __version__
├── _version.py      # Version information (generated from git tags at build time)
└── core.py          # Core functionality (greet function)
```

## Type Hints

All public APIs include type hints for better IDE support and type checking:

```python
from bastproxy import greet

# Type checkers will infer the correct types
message: str = greet("Python")
```

## Extending the Package

This template provides a starting point. To add your own functionality:

### Adding a New Module

1. Create a new file in `src/bastproxy/`:
   ```python
   # src/bastproxy/new_module.py
   """New module description."""

   def new_function(param: str) -> str:
       """Function documentation."""
       return f"Processed: {param}"
   ```

2. Export it in `__init__.py`:
   ```python
   from .new_module import new_function

   __all__ = ["__version__", "greet", "new_function"]
   ```

3. Add tests in `tests/`:
   ```python
   # tests/test_new_module.py
   from bastproxy import new_function

   def test_new_function() -> None:
       """Test new_function."""
       assert new_function("test") == "Processed: test"
   ```

### Adding Exception Classes

```python
# src/bastproxy/exceptions.py
"""Package exceptions."""

class PackageError(Exception):
    """Base exception for package errors."""
    pass

class ValidationError(PackageError):
    """Raised when validation fails."""
    pass
```

Export them:

```python
# src/bastproxy/__init__.py
from .exceptions import PackageError, ValidationError

__all__ = [
    "__version__",
    "greet",
    "PackageError",
    "ValidationError",
]
```

### Adding CLI Support

1. Add `click` or `typer` to dependencies in `pyproject.toml`

2. Create CLI module:
   ```python
   # src/bastproxy/cli.py
   """Command-line interface."""
   import click
   from . import greet

   @click.command()
   @click.argument("name", default="World")
   def main(name: str) -> None:
       """Greet someone."""
       click.echo(greet(name))
   ```

3. Add entry point in `pyproject.toml`:
   ```toml
   [project.scripts]
   package-cli = "bastproxy.cli:main"
   ```

## Documentation Best Practices

When adding new functions or classes:

1. **Always include type hints**:
   ```python
   def process(data: str, validate: bool = True) -> dict[str, Any]:
       """Process data."""
   ```

2. **Write comprehensive docstrings**:
   ```python
   def process(data: str, validate: bool = True) -> dict[str, Any]:
       """Process input data.

       Args:
           data: The input data to process.
           validate: Whether to validate the data. Defaults to True.

       Returns:
           A dictionary containing the processed results.

       Raises:
           ValueError: If validation fails and validate is True.

       Example:
           >>> process("test")
           {'result': 'test'}
       """
   ```

3. **Include examples in docstrings**

4. **Update this API documentation**

5. **Add tests for all new functionality**

## Testing

All public APIs should have comprehensive tests:

```bash
# Run all tests
uv run pytest -v

# Run with coverage
uv run pytest --cov=bastproxy --cov-report=term-missing

# Run specific test
uv run pytest tests/test_example.py::test_version -v
```

## Type Checking

Run mypy to verify type hints:

```bash
# Check entire source
uv run mypy src/

# Check specific file
uv run mypy src/bastproxy/core.py
```

## Changelog

See [CHANGELOG.md](https://github.com/endavis/bastproxy/blob/main/CHANGELOG.md) for version history and changes.

## Contributing

See [CONTRIBUTING.md](https://github.com/endavis/bastproxy/blob/main/.github/CONTRIBUTING.md) for information on contributing to the API.
