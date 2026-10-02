# Toffee

Toffee runs Terraform once per environment. You name the environment, and
Toffee selects its variable file, backend settings, and local Terraform data
directory. The current version is 1.1.0.

```bash
toffee dev init
toffee dev plan
toffee dev check
toffee prod apply
```

## Install

Requires Python 3.10 or newer and Terraform 1.5 or newer.

```bash
pipx install git+https://github.com/akhileshmishrabiz/toffee-terraform-wrapper.git
```

```bash
uv tool install git+https://github.com/akhileshmishrabiz/toffee-terraform-wrapper.git
```

Upgrade later with `pipx upgrade toffee` or `uv tool upgrade toffee`.

From a local clone:

```bash
git clone https://github.com/akhileshmishrabiz/toffee-terraform-wrapper.git
cd toffee-terraform-wrapper
python3 -m venv .venv
. .venv/bin/activate
python -m pip install .
```

## Start

```bash
toffee new service
cd service
```

This creates a small AWS project with an S3 backend, the `us-east-1` region,
and a `dev` environment. Open `service/vars/dev.tfbackend` and replace
`CHANGE-ME` with your state bucket. The state key is
`service/dev/terraform.tfstate`.

```bash
toffee dev init
toffee dev validate
toffee dev check
toffee dev plan
toffee dev apply
```

Use your normal AWS credentials. Do not put them in Terraform or Toffee files.
`toffee new` never overwrites an existing file. In a directory that already
has Terraform files, it adds only the Toffee files.

## Add an environment

Each environment is a pair of files:

```text
vars/dev.tfvars
vars/dev.tfbackend
vars/prod.tfvars
vars/prod.tfbackend
```

The `.tfvars` file holds input values. The `.tfbackend` file holds backend
settings, including a state key that belongs only to that environment.

```bash
toffee env create staging
toffee env copy dev prod
```

After a copy, check that the new files have the right values and a different
state key. An existing root module needs a partial backend block:

```hcl
terraform {
  required_version = ">= 1.5"

  backend "s3" {}
}
```

## Run

```text
toffee <environment>[,<environment>...] <terraform-command> [arguments]
```

Terraform arguments pass through unchanged:

```bash
toffee dev plan -target=aws_instance.web
toffee prod apply
toffee dev,staging plan
toffee dev,staging plan --parallel
```

Toffee adds three things for you:

- `-backend-config=vars/<env>.tfbackend` on `init`
- `-var-file=vars/<env>.tfvars` on commands that accept it
- `TF_DATA_DIR=.toffee/terraform-data/<env>`

`--parallel` runs environments at the same time. `init` stays one at a time.
A sequential run stops at the first failure. A saved plan can be applied only
by the environment that created it.

`prod` and `production` ask for confirmation before a state change. Terraform
auto-approve does not skip that question. Two environments that share state
are refused.

## Check

`fmt` and `validate` always run. Add scanners with `--checks`.

```bash
toffee dev check
toffee dev check help
toffee dev check --checks tflint,checkov
toffee dev,prod check --checks checkov
```

Checkov prints failed checks only. If it is missing, Toffee prints:

```bash
uv tool install checkov
pipx install checkov
```

TFLint is not a Python package. Toffee prints Homebrew on macOS, WinGet on
Windows, or the release archive on Linux, and also
`go install github.com/terraform-linters/tflint@latest`.

Passed lines are green. Failed lines are red. Exit 0 when everything passed,
1 when a check failed, and 2 when the arguments are wrong.

## Compare

```bash
toffee diff dev prod
```

Sensitive values are hidden. Add `--show-sensitive` to print them, or
`--exit-code` to exit 1 when the environments differ.

## Configuration

Project settings are in `.toffee.json`. Global settings are in
`~/.toffee/config.json`.

```bash
toffee config show
toffee config set auto_approve true --project
```

| Key | Meaning |
| --- | --- |
| `vars_dir` | Directory of environment files. Default `vars`. |
| `terraform_path` | Terraform executable. Default `terraform`. |
| `auto_approve` | Add Terraform's approval flag where Toffee allows it. |
| `verbose` | Extra wrapper output. |
| `protected_environments` | More names that ask for confirmation, besides `prod` and `production`. |

A project may set `terraform_path` only to `terraform`, `tofu`, or `opentofu`.
Any other path belongs in the global config or `TOFFEE_TERRAFORM_PATH`.

## Commands

| Command | What it does |
| --- | --- |
| `toffee <env> <terraform-command>` | Run that Terraform command for one environment. |
| `toffee dev,prod plan` | Run the same command for each environment, in order. |
| `toffee dev,prod plan --parallel` | Run it for each environment at the same time. |
| `toffee dev check` | Run `fmt` and `validate`. |
| `toffee dev check --checks tflint,checkov` | Also run TFLint and Checkov. |
| `toffee dev check help` | Show the check options. |
| `toffee new service` | Create a project in `service/`. |
| `toffee new` | Add Toffee files to the current directory. |
| `toffee env create staging` | Create an empty environment pair. |
| `toffee env copy dev staging` | Copy an environment and rewrite its name and state key. |
| `toffee diff dev prod` | Compare variable and backend settings. |
| `toffee info envs` | List environments. |
| `toffee info env dev` | Show one environment's file paths. |
| `toffee info commands` | List commands from the installed Terraform. |
| `toffee info version` | Show the Toffee and Terraform versions. |
| `toffee config show` | Show the current settings. |
| `toffee config init` | Create a project `.toffee.json`. |
| `toffee config set KEY VALUE` | Save a global setting. |
| `toffee config set KEY VALUE --project` | Save a project setting. |
| `toffee --version` | Show the Toffee version. |

## Development

```bash
python3 -m venv .venv
. .venv/bin/activate
python -m pip install -e ".[dev]"
pytest
ruff check .
ruff format --check .
```

See the [testing guide](TESTING.md), the [changelog](CHANGELOG.md), and the
[roadmap](ROADMAP.md).

## License

[MIT](LICENSE)
