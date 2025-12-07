# Optional Extensions

This guide covers optional tools and extensions that you can add to your project based on your specific needs.

## Testing Extensions

### pytest-watch - Auto-run tests on file changes

Automatically run tests when files change, perfect for TDD workflow.

```bash
# Add to pyproject.toml
[project.optional-dependencies]
dev = [
    # ... existing deps ...
    "pytest-watch>=4.2",
]

# Install
uv sync

# Usage
uv run ptw
```

### hypothesis - Property-based testing

Generate test cases automatically based on property specifications.

```bash
# Add to pyproject.toml
[project.optional-dependencies]
dev = [
    # ... existing deps ...
    "hypothesis>=6.0",
]

# Install
uv sync
```

Example test:

```python
from hypothesis import given
from hypothesis import strategies as st

@given(st.integers(), st.integers())
def test_addition_commutative(a, b):
    assert a + b == b + a
```

### faker - Generate realistic fake data

Create realistic test data for your tests.

```bash
# Add to pyproject.toml
[project.optional-dependencies]
dev = [
    # ... existing deps ...
    "faker>=20.0",
]

# Install
uv sync
```

Example usage:

```python
from faker import Faker

fake = Faker()
email = fake.email()
name = fake.name()
address = fake.address()
```

### factory-boy - Test fixtures/factories

Build complex test objects with minimal boilerplate.

```bash
# Add to pyproject.toml
[project.optional-dependencies]
dev = [
    # ... existing deps ...
    "factory-boy>=3.3",
]

# Install
uv sync
```

Example:

```python
import factory

class UserFactory(factory.Factory):
    class Meta:
        model = User

    username = factory.Sequence(lambda n: f"user{n}")
    email = factory.LazyAttribute(lambda obj: f"{obj.username}@example.com")
```

### mutmut - Mutation testing

Test your tests by introducing bugs and verifying they catch them.

```bash
# Add to pyproject.toml
[project.optional-dependencies]
dev = [
    # ... existing deps ...
    "mutmut>=2.4",
]

# Install
uv sync

# Usage
uv run mutmut run
uv run mutmut results
```

### vcrpy - Record and replay HTTP interactions

Record HTTP interactions once and replay them in tests for faster, deterministic testing.

```bash
# Add to pyproject.toml
[project.optional-dependencies]
dev = [
    # ... existing deps ...
    "vcrpy>=5.0",
    "pytest-vcr>=1.0",  # pytest integration
]

# Install
uv sync
```

Example:

```python
import vcr

@vcr.use_cassette('fixtures/vcr_cassettes/api_call.yaml')
def test_api_call():
    response = requests.get('https://api.example.com/data')
    assert response.status_code == 200
```

## Performance & Profiling

### py-spy - Low-overhead sampling profiler

Profile your Python code with minimal performance impact.

```bash
# Install globally (not as project dependency)
pip install py-spy

# Usage
py-spy record -o profile.svg -- python your_script.py
py-spy top -- python your_script.py
```

### memray - Memory profiler

Track memory allocations and find memory leaks.

```bash
# Install
pip install memray

# Usage
memray run your_script.py
memray flamegraph memray-output.bin
```

### scalene - CPU+GPU+memory profiler

Comprehensive profiling showing CPU, GPU, and memory usage.

```bash
# Install
pip install scalene

# Usage
scalene your_script.py
```

### line_profiler - Line-by-line profiling

See exactly which lines are slow.

```bash
# Install
pip install line_profiler

# Usage - add @profile decorator to functions
kernprof -l -v your_script.py
```

### Profiling task automation

Add profiling tasks to `dodo.py`:

```python
def task_profile():
    """Profile the application."""
    return {
        "actions": [
            "uv run py-spy record -o tmp/profile.svg -- python -m bastproxy",
        ],
        "title": title_with_actions,
    }

def task_profile_memory():
    """Profile memory usage."""
    return {
        "actions": [
            "memray run -o tmp/memray.bin python -m bastproxy",
            "memray flamegraph tmp/memray.bin -o tmp/memray.html",
        ],
        "title": title_with_actions,
    }
```

## Configuration Management

### pydantic-settings - Type-safe configuration

Load and validate configuration from environment variables.

```bash
# Add to pyproject.toml
dependencies = [
    "pydantic>=2.0",
    "pydantic-settings>=2.0",
]

# Install
uv sync
```

Example:

```python
from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    api_key: str
    debug: bool = False
    max_connections: int = 10

    class Config:
        env_file = ".env"

settings = Settings()
```

### dynaconf - Multi-environment configuration

Manage settings across development, staging, and production environments.

```bash
# Add to pyproject.toml
dependencies = [
    "dynaconf>=3.2",
]

# Install
uv sync
```

Example structure:

```
settings/
  ├── settings.toml      # Default settings
  ├── .secrets.toml      # Sensitive data (git-ignored)
  └── development.toml   # Development overrides
```

### python-decouple - Strict separation of settings

Simple, strict separation of settings from code.

```bash
# Add to pyproject.toml
dependencies = [
    "python-decouple>=3.8",
]

# Install
uv sync
```

Example:

```python
from decouple import config

DEBUG = config('DEBUG', default=False, cast=bool)
DATABASE_URL = config('DATABASE_URL')
```

## Logging & Monitoring

### loguru - Simplified logging

Easy-to-use logging with sensible defaults.

```bash
# Add to pyproject.toml
dependencies = [
    "loguru>=0.7",
]

# Install
uv sync
```

Example:

```python
from loguru import logger

logger.add("app.log", rotation="500 MB")
logger.info("Application started")
logger.error("An error occurred")
```

### structlog - Structured logging

Output structured, machine-readable logs.

```bash
# Add to pyproject.toml
dependencies = [
    "structlog>=24.0",
]

# Install
uv sync
```

Example:

```python
import structlog

log = structlog.get_logger()
log.info("user_action", user_id=123, action="login")
```

### Sentry integration - Error tracking

Automatically capture and report errors.

```bash
# Add to pyproject.toml
dependencies = [
    "sentry-sdk>=1.40",
]

# Install
uv sync
```

Example:

```python
import sentry_sdk

sentry_sdk.init(
    dsn="your-dsn-here",
    traces_sample_rate=1.0,
)
```

### OpenTelemetry - Observability

Complete observability with traces, metrics, and logs.

```bash
# Add to pyproject.toml
dependencies = [
    "opentelemetry-api>=1.20",
    "opentelemetry-sdk>=1.20",
]

# Install
uv sync
```

## Dependency Management

### pipdeptree - Visualize dependency tree

See your dependency tree and identify conflicts.

```bash
# Add to pyproject.toml
[project.optional-dependencies]
dev = [
    # ... existing deps ...
    "pipdeptree>=2.13",
]

# Install and use
uv sync
uv run pipdeptree
uv run pipdeptree --reverse  # Show what depends on a package
```

## Additional Code Quality Tools

### vulture - Dead code detection

Find unused code in your project.

```bash
# Add to pyproject.toml
[project.optional-dependencies]
dev = [
    # ... existing deps ...
    "vulture>=2.10",
]

# Install and use
uv sync
uv run vulture src/
```

Add to `dodo.py`:

```python
def task_dead_code():
    """Find dead code with vulture."""
    return {
        "actions": ["uv run vulture src/"],
        "title": title_with_actions,
    }
```

### radon - Code complexity metrics

Measure cyclomatic complexity and maintainability.

```bash
# Add to pyproject.toml
[project.optional-dependencies]
dev = [
    # ... existing deps ...
    "radon>=6.0",
]

# Install and use
uv sync
uv run radon cc src/ -a  # Cyclomatic complexity
uv run radon mi src/     # Maintainability index
```

### interrogate - Docstring coverage

Measure documentation coverage.

```bash
# Add to pyproject.toml
[project.optional-dependencies]
dev = [
    # ... existing deps ...
    "interrogate>=1.5",
]

# Install and use
uv sync
uv run interrogate src/
```

Configuration in `pyproject.toml`:

```toml
[tool.interrogate]
ignore-init-method = true
ignore-init-module = false
ignore-magic = true
ignore-semiprivate = false
ignore-private = false
ignore-property-decorators = false
ignore-module = false
fail-under = 80
verbose = 2
```

## Container Support

### Basic Dockerfile

Create a `Dockerfile` for containerized deployment:

```dockerfile
FROM python:3.12-slim

WORKDIR /app

# Install uv
RUN pip install uv

# Copy dependency files
COPY pyproject.toml uv.lock ./

# Install dependencies
RUN uv sync --no-dev

# Copy application code
COPY src/ ./src/

# Run the application
CMD ["uv", "run", "python", "-m", "bastproxy"]
```

### Docker Compose for development

Create `docker-compose.yml` for local development:

```yaml
version: '3.8'

services:
  app:
    build: .
    volumes:
      - ./src:/app/src
      - ./tests:/app/tests
    environment:
      - DEBUG=true
    ports:
      - "8000:8000"
```

## Multi-version Testing with tox

Test your package across multiple Python versions.

```bash
# Add to pyproject.toml
[project.optional-dependencies]
dev = [
    # ... existing deps ...
    "tox>=4.0",
]

# Install
uv sync
```

Create `tox.ini`:

```ini
[tox]
envlist = py312,py313

[testenv]
deps =
    pytest>=8.0
    pytest-cov>=5.0
commands =
    pytest {posargs}

[testenv:lint]
deps =
    ruff>=0.5
commands =
    ruff check src/ tests/
```

Usage:

```bash
uv run tox          # Run all environments
uv run tox -e py312 # Run specific environment
uv run tox -e lint  # Run linting
```

## Alternative: nox for testing

More flexible than tox, uses Python for configuration.

```bash
# Add to pyproject.toml
[project.optional-dependencies]
dev = [
    # ... existing deps ...
    "nox>=2023.0",
]

# Install
uv sync
```

Create `noxfile.py`:

```python
import nox

@nox.session(python=["3.12", "3.13"])
def tests(session):
    session.install(".[dev]")
    session.run("pytest")

@nox.session
def lint(session):
    session.install("ruff")
    session.run("ruff", "check", "src/", "tests/")
```

Usage:

```bash
uv run nox          # Run all sessions
uv run nox -s tests # Run specific session
```

## Summary

This template provides a solid foundation with the most commonly needed tools. Add extensions from this guide as your project grows and your needs evolve.

### Quick Reference: When to Add What

- **Testing extensions**: When you have complex test scenarios or want to improve test coverage
- **Profiling tools**: When you identify performance issues and need to optimize
- **Configuration management**: When you need multi-environment support or complex settings
- **Logging/monitoring**: When deploying to production and need observability
- **Containers**: When you need consistent deployment environments
- **Multi-version testing**: When releasing a library that must support multiple Python versions

Remember: Start simple, add complexity only when needed.
