# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

## [Unreleased]

### Added

- Add `toffee new [DIRECTORY]` to scaffold a Terraform project for Toffee
  without prompts: `main.tf`, `variables.tf`, `outputs.tf`, `versions.tf`,
  `providers.tf`, `data.tf`, `modules/`, `vars/<env>.tfvars` and
  `vars/<env>.tfbackend` with a unique state key per environment,
  `.toffee.json`, and `.gitignore`. Options are `--envs`, `--provider`
  (`aws`, `google`, `azurerm`, `none`), `--backend` (`s3`, `gcs`, `azurerm`,
  `local`; defaults to match the provider), `--region`, `--name`, `--agents`
  (writes `AGENTS.md`), `--dry-run`, and `--template <local dir>` with
  `{{token}}` substitution and per-environment `__env__` paths. It never
  overwrites files, appends only missing `.gitignore` lines, and in a
  directory that already has `.tf` files adds only Toffee's files. It prints
  a compact file tree and at most three next steps.
- `toffee <env> init` stops with a one-line error naming the file and setting
  while the environment's `.tfbackend` still contains the `CHANGE-ME`
  placeholder, unless the value is passed with `-backend-config`.
- Require an explicit Toffee confirmation before applying to or destroying
  `prod` and `production`, even when automatic approval is enabled, and show a
  credential-safe backend destination before confirmation.
- Add `toffee diff <source> <target>` to compare top-level `.tfvars` and
  `.tfbackend` settings between environments, with sensitive values redacted by
  default.
- Add the `protected_environments` project setting to protect more environment
  names in addition to `prod` and `production`.
- Record the environment and SHA-256 of every saved plan written by
  `toffee <env> plan -out=FILE` in `FILE.toffee.json`, signed with a per-user
  key in `~/.toffee/plan-signing.key`.
- Add `toffee diff --exit-code`, which exits with 1 when environments differ
  and 2 on errors.
- Add the `TOFFEE_TERRAFORM_PATH` environment variable to choose the Terraform
  binary, taking precedence over configuration files.
- Support running Toffee with `python -m toffee`.

### Changed

- `new` is a reserved environment name, and the reserved-name error lists
  every reserved name.
- Extend the protected confirmation to `refresh`, `import`, `taint`,
  `untaint`, `force-unlock`, `test`, `apply -destroy`, `state rm`, `state mv`,
  `state push`, `state replace-provider`, and `workspace delete`.
- The protected confirmation lists every target of a multi-environment
  command, highlighting the protected ones.
- The non-protected destroy warning and prompt are written to stderr.
- Parallel runs close Terraform's stdin, add `-input=false` to commands that
  accept it unless `-input` is given, and require `-auto-approve` for
  `destroy` and `apply -destroy`.
- `toffee <env> <command> --help` shows Terraform's help instead of Toffee's.
- Environment file paths are passed to Terraform relative to its working
  directory (or `-chdir` directory) instead of as absolute paths.
- Invalid configuration (a non-object file, invalid JSON, or wrongly typed
  known settings such as `"auto_approve": "false"`) is reported as an error
  instead of being ignored or partly applied.
- `config set` writes only explicitly set global values, preserves other keys
  in `.toffee.json`, and replaces files atomically.
- Require Python 3.10 or newer and click 8.2 or newer. Python 3.8 and 3.9 are
  end-of-life, and the test suite relies on click 8.2 behavior.
- `env copy` rewrites only quoted values equal to the source name and
  environment-named segments of backend `key`, `prefix`, and `path` values,
  prints each rewrite, and lists only the files it wrote.

### Security

- Reject empty or whitespace-only arguments, which let
  `toffee prod "" apply` skip the production confirmation.
- Refuse to apply a saved plan through an environment other than the one it
  was created for, or after the plan file changed. Plan records are
  authenticated with an HMAC over the environment name and plan hash, using a
  random `0600` key in `~/.toffee/`. Plans without a record, or whose record
  was edited, is unsigned, or was signed by another user or machine, require
  the protected confirmation when the project has a protected environment.
- Refuse to run commands that can read or write state when a target shares
  backend state with another environment, and refuse any command when its
  files resolve to another environment's files. Commands that never touch
  state (such as `fmt`, `validate`, `version`, `providers lock`, and any
  `-help`) are not blocked by shared state. If the root module cannot be
  parsed, environments are compared by their non-credential backend settings
  and Terraform reports the syntax error; another environment's unparsable
  `.tfbackend` is skipped with a warning. Local state paths are compared
  case-insensitively on macOS and Windows but shown in their original case.
- `env copy` and `env create` refuse names that differ only by case from an
  existing environment, which overwrote `prod` on case-insensitive file
  systems, and never write through symlinks.
- `env copy` refuses, before writing anything, when the copy would share state
  with an existing environment.
- `toffee diff` redacts many more sensitive names (such as `api_key`,
  `db_pass`, `pwd`, `auth`, `conn_str`, `database_url`, `ssh_key`,
  `webhook_url`, and `github_pat`), maps and lists containing a sensitive key,
  and URLs with embedded credentials.
- `toffee diff` replaces C1 control and invisible formatting characters, such
  as bidirectional overrides, before printing values.
- The `Running:` status line hides `-var` values and inline `-backend-config`
  `key=value` values, and no longer interprets arguments as Rich markup.
- A project `.toffee.json` can set `terraform_path` only to `terraform`,
  `tofu`, or `opentofu` (optionally with a version suffix such as
  `terraform1.9`) on `PATH`, so a cloned repository can no longer choose which
  binary Toffee runs, or name an interpreter such as `sh` that would run a
  repository file named after the Terraform command. Other names and explicit
  paths must come from `~/.toffee/config.json` or `TOFFEE_TERRAFORM_PATH`.
- `info envs` renders environment and file names as plain text with control
  characters replaced, so file names cannot inject terminal markup.

### Fixed

- `env copy` and `env create` no longer wrap long file paths when output is not
  a terminal.
- `apply -destroy` no longer receives `-auto-approve` from the `auto_approve`
  setting.
- The `auto_approve` setting inserts `-auto-approve` before a positional
  argument, respects an explicit `-auto-approve=false`, and is not added when
  applying a saved plan.
- Only the first positional argument of `apply` is treated as a saved plan, and
  only if it is a plan file, so `-var-file extra.tfvars` and `-target` values
  no longer drop the environment's variable file.
- Closed stdin at a confirmation prompt aborts cleanly instead of raising an
  error.
- `toffee diff` compares heredoc values instead of reading their bodies as
  settings, ignores `/* */` comments, and reports unterminated blocks,
  assignments without a value (such as `x =`), and unreadable files as errors
  instead of silently merging, comparing an empty value, or crashing.
- Parallel commands no longer hang on invisible prompts.
- Parallel output is written as raw bytes with stdout and stderr kept
  separate, so JSON output is not corrupted by line wrapping, emoji
  replacement, merged stderr, or invalid UTF-8.
- With `-detailed-exitcode`, exit code 2 no longer stops sequential runs, and
  a parallel failure is no longer masked by another environment's exit code 2.
- Ctrl-C no longer makes Toffee exit while Terraform is still shutting down,
  and `SIGTERM` is forwarded to Terraform.
- `init` works when the project path contains a symlink, such as macOS `/tmp`.
- A supplemental `-backend-config=key=value` no longer drops the
  environment's backend file and `-reconfigure`.
- Arguments such as `-var 'cidrs=[/]'` no longer crash the status line.
- The backend shown in the protected confirmation ignores commented-out
  blocks, supports `.tf.json` files and unquoted backend labels, and honors
  `-chdir`.
- Toffee no longer crashes when `HOME` is read-only; `~/.toffee/` is created
  only when saving global configuration or recording a saved plan.
- `config set` reports save failures with a non-zero exit code, refuses to
  overwrite a configuration file it could not parse, and no longer crashes on
  values containing Rich markup.
- Environment names with a trailing newline are rejected, and names that
  commands reject (such as `config`, `dev.eu`, or `my env`) are no longer
  listed.
- Builds require setuptools 61 or newer, which prevents an empty
  `UNKNOWN-0.0.0` wheel, and the version is defined once in
  `toffee/__init__.py`.
- Tests no longer read or write the real `~/.toffee`, and the integration test
  runs this checkout instead of whichever `toffee` is on `PATH`. CI installs
  Terraform so the integration test runs, tests Python 3.10 through 3.13, and
  runs on every pull request.
- The example1 prod backend uses the same region as its state bucket.
