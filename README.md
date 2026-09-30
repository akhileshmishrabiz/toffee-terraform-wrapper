# Toffee

Toffee is a small, environment-first Terraform wrapper. It keeps normal
Terraform commands and arguments while automatically selecting each
environment's variable file, backend settings, and local Terraform data
directory. This makes `dev`, `staging`, and `prod` explicit without Terraform
workspaces or repeated `-var-file` and `-backend-config` flags.
The current version is 1.0.0.

```bash
toffee dev init
toffee dev plan
toffee prod apply
```

## Environment model

Each environment is a pair of files:

```text
vars/
├── dev.tfvars
├── dev.tfbackend
├── prod.tfvars
└── prod.tfbackend
```

The `.tfvars` file contains Terraform input values. The `.tfbackend` file
contains backend settings, including a state key that must be unique to the
environment.

Toffee also sets a separate `TF_DATA_DIR` for each target:

```text
.toffee/terraform-data/dev/
.toffee/terraform-data/prod/
```

This prevents one environment's `init` from replacing another environment's
local backend metadata.

## Installation

### Requirements

- Python 3.10 or newer
- Terraform 1.5 or newer

Terraform-compatible CLIs can be selected in configuration, but OpenTofu is
not claimed as tested for this release.

Install as an isolated command with `pipx`:

```bash
pipx install git+https://github.com/akhileshmishrabiz/toffee-terraform-wrapper.git
toffee --version
```

Or with `uv`:

```bash
uv tool install git+https://github.com/akhileshmishrabiz/toffee-terraform-wrapper.git
toffee --version
```

Upgrade later with the same tool:

```bash
pipx upgrade toffee
# or
uv tool upgrade toffee
```

To install from a local clone:

```bash
git clone https://github.com/akhileshmishrabiz/toffee-terraform-wrapper.git
cd toffee-terraform-wrapper
python3 -m venv .venv
. .venv/bin/activate
python -m pip install .
toffee --version
```

## Quick start

Create a project:

```bash
toffee new service
cd service
```

`toffee new` always creates one compact AWS project with an S3 backend, the
`us-east-1` region, and a `dev` environment:

```text
service/
├── modules/
│   └── .gitkeep
├── main.tf
├── outputs.tf
├── variables.tf
├── versions.tf
├── providers.tf
├── data.tf
├── vars/
│   ├── dev.tfvars
│   └── dev.tfbackend
├── .toffee.json
└── .gitignore
```

Open `service/vars/dev.tfbackend` and replace `CHANGE-ME` with the name of your
S3 state bucket. Toffee refuses to initialize while that placeholder remains.
The generated state key is `service/dev/terraform.tfstate`.

Configure AWS credentials through the normal AWS credential chain or
environment variables. Do not put credentials in Terraform or Toffee files.

Then run:

```bash
toffee dev init
toffee dev validate
toffee dev plan
toffee dev apply
```

Run `toffee new` without a directory to scaffold the current directory.
Existing files are never overwritten. In an existing Terraform root module,
the command adds only the Toffee environment files, configuration, and
`.gitignore` entries.

## Existing projects

Toffee works with a normal Terraform root module. It needs a partial backend
block:

```hcl
terraform {
  required_version = ">= 1.5"

  backend "s3" {}
}
```

Add paired files for each environment:

```text
vars/dev.tfvars
vars/dev.tfbackend
vars/prod.tfvars
vars/prod.tfbackend
```

For example:

```hcl
# vars/dev.tfvars
environment = "dev"
region      = "us-east-1"
```

```hcl
# vars/dev.tfbackend
bucket  = "my-terraform-state"
key     = "my-service/dev/terraform.tfstate"
region  = "us-east-1"
encrypt = true
```

Every environment must use a different state destination. Toffee refuses
state-reading and state-changing commands when two environments share state.

Create an empty pair or copy an existing environment:

```bash
toffee env create dev
toffee env copy dev staging
toffee info envs
toffee info env staging
```

After copying, review both files and confirm that the new environment has the
right values and a unique state key.

## Command usage

The main syntax is:

```text
toffee <environment>[,<environment>...] <terraform-command> [terraform-args]
```

Terraform commands and arguments pass through unchanged:

```bash
toffee dev plan -target=aws_instance.web
toffee dev apply -auto-approve
toffee prod state list
toffee prod import aws_instance.web i-123
toffee dev providers schema -json
toffee dev -compact-warnings plan
```

Toffee automatically adds:

- `-backend-config=vars/<env>.tfbackend` to `init`
- `-var-file=vars/<env>.tfvars` where Terraform accepts variable files
- `TF_DATA_DIR=.toffee/terraform-data/<env>` to every subprocess

Unknown Terraform commands are also passed through, so newer Terraform
versions do not need a matching Toffee release.

### Multiple environments

Targets are comma-separated:

```bash
toffee dev,staging init
toffee dev,staging plan
toffee dev,staging plan --parallel
```

Sequential execution stops at the first failure. `--parallel` runs eligible
commands concurrently, but `init` remains serialized because environments
share `.terraform.lock.hcl`. Interactive parallel commands are rejected.
Parallel apply or destroy requires Terraform's non-interactive approval flag.

### Compare environments

Compare top-level variable and backend mappings without running Terraform:

```bash
toffee diff dev prod
toffee diff dev prod --exit-code
toffee diff dev prod --show-sensitive
```

Sensitive-looking values are redacted by default. `--show-sensitive` prints
them, so use it carefully. `--exit-code` returns 1 when differences exist and
2 for errors.

### Information and configuration

```bash
toffee info envs
toffee info env dev
toffee info commands
toffee info version

toffee config show
toffee config init
toffee config set auto_approve true --project
```

`info env` shows paths, not file contents, because environment files may
contain secrets.

## Configuration

Project configuration lives in `.toffee.json`. Global configuration lives in
`~/.toffee/config.json`.

```json
{
  "vars_dir": "vars",
  "terraform_path": "terraform",
  "auto_approve": false,
  "verbose": false,
  "protected_environments": ["critical"]
}
```

Supported keys are:

- `vars_dir`: directory containing paired environment files
- `terraform_path`: Terraform-compatible executable
- `auto_approve`: add Terraform approval where Toffee allows it
- `verbose`: enable additional wrapper output
- `protected_environments`: extra names requiring protected confirmation

Values resolve in this order:

1. built-in defaults
2. global configuration
3. project configuration
4. `TOFFEE_TERRAFORM_PATH` for the Terraform executable

Because project files are untrusted, project `terraform_path` may name only
`terraform`, `tofu`, or `opentofu`, optionally with a version suffix, and must
resolve on `PATH`. Put explicit paths or other executable names in global
configuration or `TOFFEE_TERRAFORM_PATH`.

## Safety

### Protected environments

`prod`, `production`, and names in `protected_environments` require a separate
Toffee confirmation before state-changing commands. This includes apply,
destroy, import, state mutations, and other destructive operations.

Terraform's `-auto-approve` and Toffee's `auto_approve` setting never bypass
the protected-environment confirmation.

### State isolation

Toffee validates every target before starting Terraform. It refuses commands
that can access state when environments resolve to the same backend state, and
it keeps local Terraform metadata separate through `TF_DATA_DIR`.

### Saved plans

When `toffee <env> plan -out=FILE` writes a saved plan, Toffee records the
environment and plan hash in `FILE.toffee.json`. Applying the plan through a
different environment or after the plan changes is refused. Missing, invalid,
or unverifiable records require confirmation.

### Other guarantees

- Environment files must exist as a complete `.tfvars`/`.tfbackend` pair.
- `CHANGE-ME` backend values block `init`.
- Sequential multi-environment runs stop on failure.
- Interactive commands cannot run concurrently.
- Status output goes to stderr, leaving Terraform stdout usable with `jq`.
- Credentials are not generated or stored by Toffee.

## Development

Create the development environment:

```bash
python3 -m venv .venv
. .venv/bin/activate
python -m pip install -e ".[dev]"
```

Run the checks:

```bash
pytest
ruff check .
ruff format --check .
terraform fmt -check -recursive
```

The real Terraform tests adapt a generated scaffold to a local backend so they
can validate and plan without downloading the AWS provider. See the
[testing guide](TESTING.md) for details.

Release history is in the [changelog](CHANGELOG.md). Planned work is in the
[roadmap](ROADMAP.md).

## License

[MIT](LICENSE)
