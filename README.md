# Toffee

Toffee is a thin CLI wrapper around Terraform for multi-environment workflows. It wires each environment to its own `vars/{env}.tfvars` and `vars/{env}.tfbackend` files so you can run the same Terraform commands across dev, staging, prod, and more without repeating flags.

## Why Toffee?

- Automatically injects `-var-file` and `-backend-config` for the right environment
- Run one or many environments in a single command (`dev staging prod` or `--all`)
- Optional parallel execution with `--parallel`
- Pass through any Terraform flag (`-auto-approve`, `-target=...`, etc.)
- Create and copy environments with `toffee env create` / `toffee env copy`

## Installation

```bash
pip install git+https://github.com/akhileshmishrabiz/toffee-terraform-wrapper.git
toffee --version
```

## Project Structure

```
your-terraform-project/
├── *.tf
├── .toffee.json          # optional project config
└── vars/
    ├── dev.tfvars
    ├── dev.tfbackend
    ├── prod.tfvars
    └── prod.tfbackend
```

## Quick Start

```bash
toffee env create dev
# edit vars/dev.tfvars and vars/dev.tfbackend
toffee init dev
toffee plan dev
toffee apply dev
```

## Command Reference

### Single environment

```bash
toffee init dev
toffee plan dev
toffee apply dev -auto-approve
toffee destroy dev
toffee output dev
toffee refresh dev
```

### Multiple environments

```bash
toffee plan dev staging prod
toffee apply --all
toffee plan dev staging --parallel
```

If `default_environment` is set in config, you can omit the env name:

```bash
toffee config set default_environment dev --project
toffee plan
```

### Commands without a specific environment

```bash
toffee fmt
toffee validate
toffee state list
toffee state dev list
```

### Custom Terraform commands

```bash
toffee run dev workspace list
toffee run prod import null_resource.example id
```

### Environment management

```bash
toffee env create staging
toffee env copy dev staging
toffee info envs
toffee info env prod
toffee info version
```

### Configuration

```bash
toffee config init
toffee config show
toffee config set auto_approve true
toffee config set default_environment dev --project
```

Project config (`.toffee.json`):

```json
{
  "vars_dir": "vars",
  "terraform_path": "terraform",
  "default_environment": "dev",
  "auto_approve": false,
  "verbose": false
}
```

Global config lives in `~/.toffee/config.json`.

## Testing

```bash
pip install -e ".[dev]"
pytest
```

The test suite includes a fixture Terraform project under `tests/fixtures/terraform-project/` and uses a mock `terraform` binary for fast CLI tests. Real Terraform integration tests run automatically when `terraform` is on your PATH.

## License

MIT
