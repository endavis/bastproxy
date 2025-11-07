# Testing Infrastructure

This directory contains all tests for the bastproxy project.

## Structure

- `tests/libs/` - Unit tests for library modules
- `tests/plugins/` - Unit tests for plugin modules  
- `tests/integration/` - Integration tests for component interactions

## Running Tests

### Run all tests:
```bash
pytest
```

### Run with coverage:
```bash
pytest --cov=libs --cov=plugins --cov-report=html
```

### Run specific test categories:
```bash
# Unit tests only
pytest -m unit

# Integration tests only
pytest -m integration

# Async tests
pytest -m asyncio
```

### Run specific test files:
```bash
pytest tests/libs/test_persistentdict.py
```

### Run with verbose output:
```bash
pytest -v
```

## Writing Tests

### Test File Naming
- Test files must start with `test_` or end with `_test.py`
- Test classes must start with `Test`
- Test functions must start with `test_`

### Using Fixtures
Common fixtures are defined in `conftest.py`:
- `temp_data_dir` - Temporary directory for test data
- `event_loop` - Async event loop for async tests
- `mock_api` - Mock API instance

### Example Test:
```python
def test_example(temp_data_dir):
    """Test description."""
    # Arrange
    data = {"key": "value"}
    
    # Act
    result = process(data)
    
    # Assert
    assert result == expected
```

## Coverage Reports

After running tests with coverage, open `htmlcov/index.html` to view the coverage report.

## CI/CD

Tests are automatically run on:
- Push to main branch
- Pull requests
- Before releases
