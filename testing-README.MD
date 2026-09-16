# Testing Toffee

## Setup

```bash
pip install -e ".[dev]"
```

## Commands

```bash
pytest
pytest --cov=toffee --cov-report=term-missing
ruff check .
```

## Test structure

- `tests/test_cli.py` covers the environment-first CLI, passthrough arguments,
  preflight validation, parallel safety, and isolated `TF_DATA_DIR` values.
- `tests/test_environment.py` covers environment discovery, validation, safe
  paths, and template creation.
- `tests/test_terraform_runner.py` covers the small set of arguments Toffee
  injects around otherwise unchanged Terraform commands.
- `tests/test_integration.py` uses real Terraform when available. It initializes
  dev and staging first, applies both afterward, and verifies that they create
  distinct state files.

The mock Terraform executable records both argv and `TF_DATA_DIR`, allowing CLI
tests to verify environment isolation without provisioning infrastructure.

## Adding tests

For a new wrapper behavior, test:

1. the exact Terraform argv,
2. the environment-specific `TF_DATA_DIR`,
3. failure before execution when any target is invalid, and
4. the real state location when backend behavior changes.

Do not add tests that enumerate Terraform commands. Unknown and future commands
must remain passthrough operations.
