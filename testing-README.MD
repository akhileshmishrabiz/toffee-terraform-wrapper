# Testing Toffee

## Setup

```bash
pip install -e ".[dev]"
```

Toffee supports Python 3.10 and newer. CI runs the suite on Python 3.10
through 3.13 with Terraform installed.

## Commands

```bash
pytest
pytest --cov=toffee --cov-report=term-missing
ruff check .
```

## Test structure

- `tests/test_cli.py` covers the environment-first CLI, passthrough arguments,
  preflight validation, `toffee diff`, and isolated `TF_DATA_DIR` values.
- `tests/test_guardrails.py` covers protected-environment confirmations, saved
  plan origin records, shared-state refusal, and `env copy` safety.
- `tests/test_execution.py` covers parallel output and stdin, exit code
  aggregation, `--help` passthrough, the `Running:` line, and Ctrl-C/SIGTERM
  handling with a real subprocess.
- `tests/test_config.py` covers configuration validation, the
  `terraform_path` trust rule, and saving.
- `tests/test_new.py` covers `toffee new`: the generated layout and contents,
  separate state per environment, reruns, `.gitignore` merging (checked with
  `git check-ignore`), error messages, custom templates, symlink refusal, the
  `CHANGE-ME` guard on `init`, and the user experience: a golden copy of the
  default output, help text, and running the printed next steps.
- `tests/test_environment.py` covers environment discovery, validation, safe
  paths, and template creation.
- `tests/test_environment_diff.py` covers the settings parser and redaction.
- `tests/test_backend.py` and `tests/test_safety.py` cover backend detection,
  state identity, and the credential-safe backend summary.
- `tests/test_terraform_runner.py` covers the arguments Toffee injects around
  otherwise unchanged Terraform commands.
- `tests/test_integration.py` runs this checkout with `python -m toffee`
  against real Terraform when it is on `PATH`, and is skipped otherwise. It
  initializes and applies dev and staging into distinct state files, checks
  that the empty-argument and cross-environment saved-plan bypasses are
  blocked, initializes through a symlinked project path, and initializes,
  validates, and plans a fresh `toffee new --provider none` project.

An autouse fixture gives every test a temporary `HOME` and clears
`TOFFEE_TERRAFORM_PATH`, `TF_WORKSPACE`, and `TF_DATA_DIR`, so a developer's
configuration cannot leak into the results.

The mock Terraform executable (`tests/fixtures/mock_terraform.sh`) is passed
through `TOFFEE_TERRAFORM_PATH`. It records argv and `TF_DATA_DIR`, writes a
zip-signature file for `plan -out`, and can be steered with:

- `MOCK_TF_EXIT` or `MOCK_TF_EXIT_<env>`: the exit code, for all or one
  environment;
- `MOCK_TF_STDOUT` and `MOCK_TF_STDERR`: extra output (`MOCK_TF_STDOUT` is
  printed with `printf %b`).

## Adding tests

For a new wrapper behavior, test:

1. the exact Terraform argv,
2. the environment-specific `TF_DATA_DIR`,
3. failure before execution when any target is invalid, and
4. the real state location when backend behavior changes.

For a new guardrail, also check that the test fails when the guard is
weakened, for example by checking only the first target or skipping the check
under `--parallel`.

Do not add tests that enumerate Terraform commands. Unknown and future commands
must remain passthrough operations.
