# Testing Toffee

This document outlines the testing approach for the Toffee CLI tool.

## Test Structure

Toffee uses pytest for testing. The tests are organized into three main files:

1. **test_core.py**: Tests for the core modules (environment, terraform, config)
2. **test_commands.py**: Tests for the command handlers
3. **test_cli.py**: Tests for the CLI interface

## Setting Up the Test Environment

### Install Development Dependencies

```bash
pip install -r requirements-dev.txt
```

### Running Tests

```bash
# Run all tests
pytest

# Run tests with coverage report
pytest --cov=toffee

# Run a specific test file
pytest tests/test_core.py

# Run a specific test
pytest tests/test_core.py::test_environment_creation
```

## Test Fixtures

The `conftest.py` file includes two key test fixtures:

1. **temp_terraform_project**: Creates a temporary directory with a mock Terraform project structure, including:
   - `vars/` directory with dev and prod environment files
   - Basic Terraform files

2. **temp_config_dir**: Creates a temporary directory for Toffee configuration files to avoid modifying the user's actual config.

## Mock Testing

Many tests use the `unittest.mock` module to avoid executing actual shell commands or filesystem operations. This ensures tests are:

1. Fast
2. Isolated from the environment
3. Deterministic

## Test Categories

### Unit Tests
Tests individual components in isolation.

### Integration Tests
Tests how components work together.

### CLI Tests
Tests the command-line interface using Typer's testing utilities.

## Adding New Tests

When adding new functionality to Toffee, follow these steps to maintain test coverage:

1. Add unit tests for any new core functionality
2. Add command tests for any new command handlers
3. Add CLI tests for any new CLI commands

## Running Linting

```bash
# Run flake8
flake8 toffee tests

# Run black
black --check toffee tests

# Run isort
isort --check toffee tests
```

## Test Coverage

Aim to maintain at least 80% test coverage for all code. You can check coverage with:

```bash
pytest --cov=toffee --cov-report=term-missing
```