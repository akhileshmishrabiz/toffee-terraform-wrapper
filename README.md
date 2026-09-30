# Toffee

Toffee is an environment-first Terraform wrapper that keeps normal Terraform
commands while isolating each environment's inputs, backend metadata, and local
working data. Version 1.0.0 is the first GA-quality release of the software;
this statement does not imply that a PyPI package, GitHub release, or Git tag
has been published.

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

### Requirements and tested platforms

- Python 3.10 or newer
- Terraform available on `PATH` (or configured as described below)

```bash
terraform version
python3 --version
```

The release suite runs on Python 3.10–3.13 and Ubuntu in CI. Release
verification also uses Terraform 1.16 on macOS. Terraform-compatible CLIs such
as OpenTofu can be selected with `terraform_path`, but OpenTofu and Windows have
not been tested for this release.

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

To uninstall:

```bash
pipx uninstall toffee
# or
uv tool uninstall toffee
```

### Install from a local clone

```bash
git clone https://github.com/akhileshmishrabiz/toffee-terraform-wrapper.git
cd toffee-terraform-wrapper
python3 -m venv .venv
. .venv/bin/activate
python -m pip install .
toffee --version
```

For development, use `python -m pip install -e ".[dev]"`.

## Start a new project

```bash
toffee new my-service
# Equivalent current-directory flow:
# mkdir my-service && cd my-service && toffee new
```

```text
Created 11 files for project my-service:

my-service/
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

Next steps:
  1. Replace CHANGE-ME in my-service/vars/dev.tfbackend (bucket)
  2. cd my-service && toffee dev init
  3. toffee dev plan
```

There are no prompts. The project name comes from the directory, the backend
from the provider, and the region from the provider's usual default. Values
you must fill in are marked `CHANGE-ME` (the state bucket, plus `project_id`
for Google). `toffee <env> init` stops with a one-line error while that
environment's `.tfbackend` still contains `CHANGE-ME`, unless you pass the
value with `-backend-config`.

For a five-minute local-backend walkthrough that needs no cloud account:

```bash
toffee new demo --provider none --backend local --envs dev,prod
cd demo
toffee dev init
toffee dev validate
toffee dev plan
toffee dev apply
```

For a cloud backend, first replace every `CHANGE-ME` value, then make provider
and backend credentials available through the provider's normal environment
variables, CLI login, workload identity, or credential files. Toffee never
generates or stores cloud credentials.

| Option | Default |
| --- | --- |
| `DIRECTORY` | the current directory |
| `--envs dev,staging,prod` | `dev` |
| `--provider aws\|google\|azurerm\|none` | `aws` |
| `--backend s3\|gcs\|azurerm\|local` | matches the provider (`none` uses `local`) |
| `--region` | `us-east-1`, `us-central1`, or `eastus` |
| `--name` | the directory name |
| `--agents` | off; writes `AGENTS.md` with conventions for AI coding agents |
| `--dry-run` | off; prints the same summary with "Would create" and writes nothing |
| `--template DIR` | the built-in template |

Every environment gets its own state key (for example
`key = "my-service/prod/terraform.tfstate"`), so the shared-state check passes
on a fresh project, and `prod` and `production` are protected as usual. The
Terraform files require Terraform 1.5 or newer and pin the provider's current
major version (`aws ~> 6.0`, `google ~> 8.0`, `azurerm ~> 5.0`). The
`.gitignore` ignores state, plan files, `.terraform/`, and `.toffee/`, but not
`.terraform.lock.hcl` or `.toffee.json`.

`toffee new` never overwrites a file, so it is safe to run again. With nothing
missing it prints `Nothing to create; all files already exist`, and
`toffee new --envs staging` adds only `vars/staging.*`. Missing `.gitignore`
lines are appended. In an existing project it reuses the declared backend and
provider, and the project name, region, and environments from `vars/`. If the
directory already contains `.tf` files, it adds only Toffee's files, and each
new `.tfvars` sets only variables the root module declares.

### Custom templates

`toffee new --template ./my-template` copies a local directory instead of the
built-in template. Any path segment containing `__env__` is written once per
environment, for example `vars/__env__.tfvars`. These tokens are replaced in
UTF-8 files:

| Token | Value |
| --- | --- |
| `{{project}}` | project name |
| `{{env}}` | environment name; only in files whose path contains `__env__` |
| `{{region}}`, `{{provider}}`, `{{backend}}` | the chosen values |
| `{{vars_dir}}` | the environment files directory, usually `vars` |
| `{{placeholder}}` | `CHANGE-ME` |

Terraform interpolation (`${...}`, `%{...}`) and any other `{{...}}` text are
left unchanged. Other files are copied as they are, and `.git/` is skipped.
Toffee refuses templates that contain symlinks and never writes through a
symlink or outside the target directory. Remote templates are not supported.

## Quick start

### 1. Open your Terraform project

```bash
cd path/to/your-terraform-project
```

Your root module remains normal Terraform code. Toffee does not require wrapper
configuration files around modules. Declare the backend type in the root
module and leave its settings to the environment files:

```hcl
terraform {
  backend "s3" {}
}
```

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

Toffee rewrites `"dev"` to `"prod"` and the `dev` segment of the backend `key`
and prints each change. Review `vars/prod.tfvars` and `vars/prod.tfbackend`,
especially the backend state key, then run:

```bash
toffee prod init
toffee prod plan
```

Dev and prod now use separate variable files, backend configurations, state,
and local Terraform metadata.

## Command usage

The syntax is always:

```text
toffee <environment>[,<environment>...] <terraform-command> [terraform-args] [--parallel]
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
  environment's file, so they supplement it. Toffee parses inline values and
  local override files before `init` and refuses an effective destination that
  would share state with another environment.
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
prompt. Automation should not feed answers to this human confirmation.

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
writes `FILE.toffee.json` next to the plan with the environment name, the
plan's SHA-256 hash, and an HMAC-SHA256 signature over both. The signature uses
a random key private to your user account, `~/.toffee/plan-signing.key`, which
Toffee creates with `0600` permissions the first time it records a plan. Then
`toffee <env> apply FILE`:

- refuses if the plan was created for a different environment, or if the plan
  file changed after it was recorded;
- asks for the protected confirmation if the plan belongs to a protected
  environment;
- asks for confirmation, noting that the plan's origin cannot be verified, if
  the plan has no record or its record's signature does not verify. This
  applies even when the named environment is not protected. It includes a
  record that was edited by hand, has no signature, or was signed by another
  user or machine, and the case where the key is missing or readable by other
  users.

A signature is only valid for the user and machine that created it, so a plan
copied to another machine or CI job is unverified there and needs the
confirmation. That is the intended safe default. If Toffee cannot
create the key (for example because `HOME` is read-only), `plan -out` still
succeeds but prints a warning and writes no record.

`plan -out` and saved-plan `apply` accept only one target, since environments
would otherwise overwrite or share one plan file. Relative plan paths are
resolved against `-chdir` when it is given.

### Separate state per environment

Before running a Terraform command that can read or write state, Toffee
refuses to continue if a target would share state with any other environment.
It reads the backend type from the root module's `.tf` and `.tf.json` files
(in the `-chdir` directory, if given) and compares the settings that select the
state object, together with the workspace selected for that environment:

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
default local state, so Toffee refuses state commands there while more than one
environment has a backend file.

Commands that never touch state skip the comparison: `fmt`, `validate`,
`version` (and `-version`), `get`, `modules`, `metadata`, `providers lock`,
`providers mirror`, `login`, `logout`, and any command given `-h`, `-help`, or
`--help`. Everything else is compared, including `init`, `providers`,
`providers schema` (both read state), and commands Toffee does not know.

If Toffee cannot parse the root module, for example because of a syntax error,
it prints a warning and compares every non-credential setting in the
environments' `.tfbackend` files instead, and the protected confirmation shows
`Backend: unknown (could not parse configuration)`. Terraform then reports the
syntax error itself. Another environment's `.tfbackend` file that cannot be
parsed is left out of the comparison with a warning naming the file. A
target's own unparsable `.tfbackend` still stops state commands.

## Environment management

```bash
toffee env create dev
toffee env copy dev staging
toffee info envs
toffee info env dev
```

`info env` shows file paths but does not print file contents because Terraform
variable and backend files can contain secrets.

Environment names start with a letter or digit and contain only letters,
digits, underscores, and hyphens; `config`, `diff`, `env`, `info`, and `new`
are reserved. Files in `vars/` with other names are not listed as environments.
Names must also be unique ignoring letter case, because macOS and Windows file
systems usually treat `Prod.tfvars` and `prod.tfvars` as the same file.

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
values. A file with an unterminated string, heredoc, comment, or block, or an
assignment without a value such as `x =`, is reported as a parse error instead
of being guessed at.

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
`~/.toffee/config.json`. Project values override global values, except
`protected_environments`, where both lists are combined.

```json
{
  "vars_dir": "vars",
  "terraform_path": "terraform",
  "auto_approve": false,
  "verbose": false,
  "protected_environments": []
}
```

Both files must contain a JSON object using only the keys shown above. A typo
or unknown key is an error. `auto_approve` and `verbose` must be `true` or
`false` (not the string
`"false"`), `vars_dir` and `terraform_path` non-empty strings, and
`protected_environments` a list of names. An invalid or unreadable file is
reported as an error and Toffee exits without running anything. `config set`
never overwrites a file it could not parse, and it reports a failure if the
file cannot be written. `~/.toffee/` is only created when you save global
configuration or record a saved plan.

Because `.toffee.json` usually arrives with a cloned repository, it may set
`terraform_path` only to `terraform`, `tofu`, or `opentofu`, optionally
followed by a version such as `terraform1.9` or `tofu-1.8.3`, looked up on
`PATH`. Any other name is refused, because a name such as `sh` or `python`
would run a file from the repository (for example one named `plan`) in place
of Terraform. Set any other executable or an explicit path in
`~/.toffee/config.json`, or with the `TOFFEE_TERRAFORM_PATH` environment
variable, which takes precedence over both files:

```bash
toffee config set terraform_path /opt/terraform/1.9/terraform
TOFFEE_TERRAFORM_PATH=/opt/terraform/1.9/terraform toffee dev plan
```

Normal precedence is `TOFFEE_TERRAFORM_PATH` (for the executable only), then
project config, global config, and built-in defaults. The one merge rule is
`protected_environments`: project and global names are combined, while `prod`
and `production` are always protected. A project `vars_dir` must resolve inside
the project; a project config cannot redirect environment writes elsewhere.

## Safety guarantees

- Every target is validated before any Terraform process starts.
- Sequential multi-environment execution stops on the first failure (exit code
  2 with `-detailed-exitcode` is not a failure).
- Each environment must have both its `.tfvars` and `.tfbackend` file.
- Backend metadata is isolated per environment, and state commands for
  environments that would share state are refused.
- State-changing commands against protected environments require a separate
  Toffee confirmation that neither `-auto-approve` nor `auto_approve` bypasses.
- Saved plans with a record signed by your key are only applied to the
  environment they were created for; plans without a verifiable record require
  the protected confirmation when the project has a protected environment.
- Destruction, including `apply -destroy`, requires confirmation unless
  `-auto-approve` is supplied on the command line.
- Interactive commands cannot run concurrently, and parallel commands never
  wait on hidden prompts.
- Saved plans are applied without injecting a conflicting variable file.
- Wrapper status is written to stderr, leaving Terraform stdout usable with
  tools such as `jq`, including in parallel mode.

## Command reference

```text
toffee [--version] [--help]
toffee new [DIRECTORY] [--name NAME] [--envs LIST]
           [--provider aws|google|azurerm|none]
           [--backend s3|gcs|azurerm|local] [--region REGION]
           [--template DIR] [--agents] [--dry-run]
toffee env create NAME
toffee env copy SOURCE TARGET
toffee diff SOURCE TARGET [--show-sensitive] [--exit-code]
toffee info envs
toffee info env ENV
toffee info commands
toffee info version
toffee config init
toffee config show
toffee config set KEY VALUE [--project]
toffee ENV[,ENV...] [TERRAFORM-GLOBAL-OPTIONS] COMMAND [ARGS] [--parallel]
```

Run `toffee COMMAND --help` for internal command details. Help after an
environment target, such as `toffee dev plan --help`, belongs to Terraform.

## Shell completion

Toffee uses Click's built-in completion for command names and options. Generate
or test a completion script without modifying shell startup files (Bash
completion requires Bash 4.4 or newer):

```bash
_TOFFEE_COMPLETE=bash_source toffee > /tmp/toffee-complete.bash
_TOFFEE_COMPLETE=zsh_source toffee > /tmp/toffee-complete.zsh
_TOFFEE_COMPLETE=fish_source toffee > /tmp/toffee-complete.fish
```

For the current shell session:

```bash
eval "$(_TOFFEE_COMPLETE=bash_source toffee)"  # bash
eval "$(_TOFFEE_COMPLETE=zsh_source toffee)"   # zsh
_TOFFEE_COMPLETE=fish_source toffee | source   # fish
```

Environment names and Terraform's evolving command/option set are intentionally
not statically completed by Toffee.

## Automation and exit codes

Use Terraform's own noninteractive options and credentials. Parallel `apply`
and destroy operations require an explicit command-line `-auto-approve`, but
that flag never bypasses a protected-environment prompt. Closed stdin and EOF
fail those prompts closed; do not pipe confirmation answers in CI.

Terraform stdout is preserved byte-for-byte and wrapper status goes to stderr.
Most commands return Terraform's exit code. For `plan -detailed-exitcode`,
status 2 remains “changes present.” `toffee diff --exit-code` uses 0 for equal,
1 for different, and 2 for errors; without `--exit-code`, differences return 0
and errors return 1.

## Troubleshooting

- `Replace CHANGE-ME`: fill in the named backend setting or supply it with
  `-backend-config`, then rerun `toffee <env> init`.
- `would share Terraform state`: give every environment a different backend
  key, prefix, path, workspace, or other backend identity setting.
- `origin ... cannot be verified`: recreate the plan on this machine or
  explicitly review and confirm the unverified saved plan.
- `Missing vars/backend file`: create both `vars/<env>.tfvars` and
  `vars/<env>.tfbackend`, or use `toffee env create <env>`.
- `Invalid configuration`: fix the named JSON file and key/type. Toffee does
  not silently ignore malformed or unknown configuration.
- Terraform reports initialization is required: run `toffee <env> init`;
  Toffee keeps separate initialization metadata per environment.

## Security model and non-goals

Toffee reduces accidental cross-environment operations; it is not a security
boundary against a malicious local user, repository, Terraform binary,
provider, or module. Review Terraform plans and protect cloud credentials,
state backends, the repository, and `~/.toffee/plan-signing.key` with normal
access controls. Backend identity checks parse a practical HCL subset and
conservatively fall back when root configuration is invalid. A plan and its
sidecar can still be replaced between Toffee's verification and Terraform's
open; do not run untrusted processes concurrently in the project.

Toffee does not manage credentials, replace Terraform state locking, evaluate
Terraform expressions, or provide policy, lint, security scanning, cost,
MCP/agent, Jev assessment, or remote-template features. Checkov, TFLint,
policy/cost tooling, MCP/Jev, and remote templates remain roadmap items.

## Development

```bash
pip install -e ".[dev]"
pytest
ruff check .
ruff format --check .
```

Tests use a temporary `HOME`, so your `~/.toffee` configuration never affects
them. The real Terraform integration tests run this checkout with
`python -m toffee` and are skipped when `terraform` is not on `PATH`; CI
installs Terraform so they always run there. See the
[testing guide](TESTING.md) for details.

Release history and future plans are available in the
[changelog](CHANGELOG.md) and [roadmap](ROADMAP.md).

## License

MIT
