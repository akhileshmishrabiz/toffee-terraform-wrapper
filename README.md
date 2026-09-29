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

Empty or whitespace-only arguments are rejected. Terraform silently skips them
when choosing its subcommand, so an unset shell variable such as
`toffee prod "$UNSET" apply` could otherwise hide the real command from Toffee.

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

In parallel mode:

- Terraform's stdin is closed, and `-input=false` is added to `plan`,
  `apply`, `destroy`, `import`, and `refresh` unless you pass `-input`
  yourself, so nothing waits on a prompt you cannot see.
- `apply` requires `-auto-approve` (or a saved plan), and `destroy` or
  `apply -destroy` requires `-auto-approve` on the command line. `console` and
  `login` are rejected.
- Each environment's stdout and stderr are captured separately and written
  unchanged once it finishes, so `toffee dev,prod output -json --parallel`
  keeps valid JSON on stdout. Environment headers and status lines go to
  stderr.

With `-detailed-exitcode`, exit code 2 means "changes present" rather than
failure: sequential runs continue to the next environment, and the combined
exit code is the first real failure, otherwise 2 if any environment has
changes, otherwise 0.

Ctrl-C reaches Terraform directly, and Toffee waits for it to shut down
cleanly (and prints any captured parallel output) before exiting with
Terraform's exit code. A `SIGTERM` sent to Toffee is forwarded to Terraform.

## Automatic arguments

Toffee adds:

- `-backend-config=vars/<env>.tfbackend` and `-reconfigure` to `init`
  (`-reconfigure` is skipped when you pass `-reconfigure` or
  `-migrate-state`). Your own `-backend-config` values are appended after the
  environment's file, so they supplement it.
- `-var-file=vars/<env>.tfvars` to Terraform commands that accept variable
  files, except when applying a saved plan.
- `-auto-approve` to `apply` when the `auto_approve` setting is enabled, unless
  you pass `-auto-approve` yourself, apply a saved plan, or use `-destroy`.
- `-input=false` to commands that accept it in parallel mode.
- `TF_DATA_DIR=.toffee/terraform-data/<env>` to every Terraform subprocess.

Environment file paths are passed relative to Terraform's working directory
(the `-chdir` directory when given), which keeps them valid when the project
is reached through a symlink such as macOS `/tmp`.

All user-supplied arguments retain their relative order and form, including
space-separated flags:

```bash
toffee dev plan -var environment=test
```

`--help` and `-h` after the environment are passed to Terraform, so
`toffee dev plan --help` shows Terraform's help for `plan`. The `Running:`
status line on stderr hides `-var` values and inline `-backend-config`
`key=value` values.

## Protected environments

`prod` and `production` are protected in any letter case. Before running a
command that can change a protected environment's state, Toffee lists every
target, shows each target's backend destination, and asks on stderr:

```text
⚠ You are about to apply changes to PROD.

Environment: prod
Backend: s3://my-terraform-state/my-service/prod/terraform.tfstate

Continue? [y/N]:
```

The answer defaults to No. An empty answer or a closed stdin aborts. Neither
Terraform's `-auto-approve` nor Toffee's `auto_approve` setting skips this
prompt. A `y` piped on stdin (for example `echo y | toffee prod apply`) does
answer it, so treat piped input as an explicit confirmation.

Protected commands are `apply` (including `apply -destroy`), `destroy`,
`refresh`, `import`, `taint`, `untaint`, `force-unlock`, `test`,
`state rm|mv|push|replace-provider`, and `workspace delete`. When a
multi-environment command includes a protected target, the single prompt lists
all targets and highlights the protected ones.

To protect more environments, list them in `.toffee.json`. The list only adds
names: `prod` and `production` are always protected. Because it is a list, set
it by editing the file rather than with `toffee config set`.

```json
{
  "protected_environments": ["staging", "dr"]
}
```

### Saved plans

A saved plan changes the state it was planned against, whichever environment
you name when applying it. When `toffee <env> plan -out=FILE` succeeds, Toffee
writes `FILE.toffee.json` next to the plan with the environment name and the
plan's SHA-256 hash. Then `toffee <env> apply FILE`:

- refuses if the plan was created for a different environment, or if the plan
  file changed after it was recorded;
- asks for the protected confirmation if the plan belongs to a protected
  environment;
- asks for the protected confirmation if the plan has no record and the
  project has any protected environment, because its origin cannot be
  verified.

`plan -out` and saved-plan `apply` accept only one target, since environments
would otherwise overwrite or share one plan file. Relative plan paths are
resolved against `-chdir` when it is given.

### Separate state per environment

Before running Terraform, Toffee refuses to continue if a target would share
state with any other environment. It reads the backend type from the root
module's `.tf` and `.tf.json` files (in the `-chdir` directory, if given) and
compares the settings that select the state object, together with the
workspace selected for that environment:

| Backend | Compared settings |
| --- | --- |
| `s3` | `bucket`, `key` (and `workspace_key_prefix` outside the default workspace) |
| `gcs` | `bucket`, `prefix` |
| `azurerm` | `storage_account_name`, `container_name`, `key` |
| `local` | `path` (default `terraform.tfstate`) |
| `remote`, `cloud` | `hostname`, `organization`, `workspaces` name/prefix/tags |
| `consul` | `path` |
| `http` | `address` |
| `kubernetes` | `secret_suffix`, `namespace` |
| `pg` | `conn_str`, `schema_name` (the connection string is never printed) |
| other | every setting except credential-like ones |

Toffee also refuses to run when an environment's `.tfvars` or `.tfbackend`
file resolves, for example through a symlink, to another environment's file.
A root module without a backend block keeps every environment in the same
default local state, so Toffee refuses to run it while more than one
environment has a backend file.

## Environment management

```bash
toffee env create dev
toffee env copy dev staging
toffee info envs
toffee info env dev
```

`info env` shows file paths but does not print file contents because Terraform
variable and backend files can contain secrets.

Environment names must be unique ignoring letter case, because macOS and
Windows file systems usually treat `Prod.tfvars` and `prod.tfvars` as the same
file.

`env copy` rewrites only quoted values exactly equal to the source name (for
example `environment = "dev"`) and, in the backend file, path segments or file
name stems equal to the source name inside `key`, `prefix`, and `path` (for
example `dev/terraform.tfstate` or `dev.tfstate`). It prints every rewrite so
you can review it. It refuses, before writing anything, when the copy would
share state with an existing environment. It never writes through a symlink,
and it only moves the new files into place once both have been written.

### Compare environments

```bash
toffee diff dev prod
```

This compares the top-level mappings in both environments' `.tfvars` and
`.tfbackend` files without running Terraform. Only changed settings are shown.
Comments (`#`, `//`, `/* */`) are ignored and heredoc bodies are compared as
values. A file with an unterminated string, heredoc, comment, or block is
reported as an error instead of being guessed at.

Values are redacted by default when the setting's name looks sensitive (for
example `password`, `db_pass`, `api_key`, `token`, `auth`, `conn_str`,
`database_url`, `ssh_key`, `webhook_url`, or `github_pat`), when a map or list
contains such a key at any depth, or when a URL embeds credentials. Use
`--show-sensitive` only when explicitly needed. Control and invisible
formatting characters are replaced before printing.

`toffee diff` exits with status 0 by default. With `--exit-code` it exits with
1 when the environments differ and 2 on errors, like `diff`:

```bash
toffee diff staging prod --exit-code || echo "staging and prod differ"
```

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
- Backend metadata is isolated per environment, and environments that would
  share state are refused.
- State-changing commands against protected environments require a separate
  Toffee confirmation that neither `-auto-approve` nor `auto_approve` bypasses.
- Saved plans are only applied to the environment they were created for.
- Destruction, including `apply -destroy`, requires confirmation unless
  `-auto-approve` is supplied on the command line.
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

Release history and future plans are available in the
[changelog](CHANGELOG.md) and [roadmap](ROADMAP.md).

## License

MIT
