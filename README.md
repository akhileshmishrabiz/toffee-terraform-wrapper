# Toffee

Toffee is a small, environment-first Terraform wrapper. It keeps Terraform
commands unchanged while isolating backend metadata for every environment.

```bash
toffee dev init
toffee dev plan
toffee prod apply
```

No Terraform workspaces, command registry, or repeated `-var-file` and
`-backend-config` arguments are required.

## Environment model

Each environment is a pair of files:

```text
vars/
├── dev.tfvars
├── dev.tfbackend
├── prod.tfvars
└── prod.tfbackend
```

Toffee sets a separate `TF_DATA_DIR` for every target:

```text
.toffee/terraform-data/dev/
.toffee/terraform-data/prod/
```

This prevents one environment's `init` from replacing another environment's
backend metadata. Add `.toffee/` to the project `.gitignore`.

## Installation

### Prerequisites

- Python 3.8 or newer
- Terraform available on `PATH`

```bash
terraform version
python3 --version
```

### Recommended: install as an isolated CLI

Using `pipx`:

```bash
pipx install git+https://github.com/akhileshmishrabiz/toffee-terraform-wrapper.git
toffee --version
```

Or using `uv`:

```bash
uv tool install git+https://github.com/akhileshmishrabiz/toffee-terraform-wrapper.git
toffee --version
```

To upgrade later:

```bash
pipx upgrade toffee
# or
uv tool upgrade toffee
```

### Install from a local clone

```bash
git clone https://github.com/akhileshmishrabiz/toffee-terraform-wrapper.git
cd toffee-terraform-wrapper
python3 -m pip install .
toffee --version
```

## Quick start

### 1. Open your Terraform project

```bash
cd path/to/your-terraform-project
```

Your root module remains normal Terraform code. Toffee does not require wrapper
configuration files around modules.

### 2. Create an environment

```bash
toffee env create dev
```

This creates:

```text
vars/dev.tfvars
vars/dev.tfbackend
```

Edit `vars/dev.tfvars` with the environment's input variables:

```hcl
environment = "dev"
region      = "us-east-1"
```

Edit `vars/dev.tfbackend` with that environment's backend:

```hcl
bucket  = "my-terraform-state"
key     = "my-service/dev/terraform.tfstate"
region  = "us-east-1"
encrypt = true
```

Do not commit credentials to either file. Use your cloud provider's normal
environment variables or credential chain.

### 3. Initialize and use the environment

```bash
toffee dev init
toffee dev validate
toffee dev plan
toffee dev apply
```

### 4. Add another isolated environment

```bash
toffee env copy dev prod
```

Update `vars/prod.tfvars` and `vars/prod.tfbackend`, especially the backend
state key, then run:

```bash
toffee prod init
toffee prod plan
```

Dev and prod now use separate variable files, backend configurations, state,
and local Terraform metadata.

## Command usage

The syntax is always:

```text
toffee <environment>[,<environment>...] <terraform-command> [terraform-args]
```

Toffee passes the Terraform command and its arguments through without needing
to know every Terraform command.

```bash
toffee dev init
toffee dev plan -target=aws_instance.web
toffee prod apply -auto-approve
toffee prod state list
toffee prod state mv old.name new.name
toffee prod import aws_instance.web i-123
toffee dev providers schema -json
toffee dev metadata functions -json
toffee dev -compact-warnings plan
```

Unknown commands are also passed through unchanged, allowing future Terraform
versions to work without a Toffee release.

### Multiple environments

Targets are explicit and comma-separated:

```bash
toffee dev,staging init
toffee dev,staging plan --parallel
toffee dev,staging apply -auto-approve --parallel
```

`init` is intentionally serialized even when `--parallel` is supplied.
Environment backend metadata is separate, but Terraform still updates the
project's shared `.terraform.lock.hcl`. Other commands can run concurrently.

Parallel interactive commands are rejected. Use `-auto-approve` for parallel
apply, or apply saved plan files.

## Automatic arguments

Toffee adds only:

- `-backend-config=vars/<env>.tfbackend` to `init`
- `-var-file=vars/<env>.tfvars` to Terraform commands that accept variable files
- `TF_DATA_DIR=.toffee/terraform-data/<env>` to every Terraform subprocess

All user-supplied arguments retain their relative order and form, including
space-separated flags:

```bash
toffee dev plan -var environment=test
```

## Environment management

```bash
toffee env create dev
toffee env copy dev staging
toffee info envs
toffee info env dev
```

`info env` shows file paths but does not print file contents because Terraform
variable and backend files can contain secrets.

### Compare environments

```bash
toffee diff dev prod
```

This compares the top-level mappings in both environments' `.tfvars` and
`.tfbackend` files without running Terraform. Only changed settings are shown.
Values whose names look sensitive are redacted by default; use
`--show-sensitive` only when explicitly needed.

## Configuration

```bash
toffee config init
toffee config show
toffee config set terraform_path tofu --project
toffee config set auto_approve true --project
```

Project configuration lives in `.toffee.json`; global configuration lives in
`~/.toffee/config.json`.

```json
{
  "vars_dir": "vars",
  "terraform_path": "terraform",
  "auto_approve": false,
  "verbose": false
}
```

## Safety guarantees

- Every target is validated before any Terraform process starts.
- Sequential multi-environment execution stops on the first failure.
- Each environment must have both its `.tfvars` and `.tfbackend` file.
- Backend metadata is isolated per environment.
- Applying to or destroying `prod` or `production` requires a separate Toffee
  confirmation.
- Neither Terraform's `-auto-approve` nor Toffee's `auto_approve` setting
  bypasses the production confirmation.
- Destruction requires confirmation unless `-auto-approve` is supplied.
- Interactive commands cannot run concurrently.
- Saved plans are applied without injecting a conflicting variable file.
- Wrapper status is written to stderr, leaving Terraform stdout usable with
  tools such as `jq`.

## Development

```bash
pip install -e ".[dev]"
pytest
ruff check .
```

Real Terraform integration tests verify that dev and staging create distinct
state files after both environments have been initialized.

## License

MIT
