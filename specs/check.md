# Spec: `toffee <env> check`

This is the contract for the unified check command. Implementation and tests
follow this document.

## Command

```text
toffee <env>[,<env>...] [terraform-global-args] check [--checks TOOLS]
```

`check` is a Toffee command. It is not passed through to Terraform.

`toffee <env> check --help` and `-h` print Toffee's help and exit 0. They do
not run Terraform and do not require the scanners to be installed.

`--parallel` is rejected. Checks run one at a time so the report stays in
order. This is a usage error (exit 2).

The only check option is `--checks` (or `--checks=TOOLS`). Any other argument
is a usage error. `--checks` may be passed once. `TOOLS` is a comma-separated
list. Surrounding whitespace is ignored. Empty names, repeated names, and
unknown names are usage errors.

## What runs

`fmt` and `validate` always run. `--checks` accepts only `tflint` and
`checkov`, in the order written. `fmt` and `validate` are not valid `--checks`
values because they always run.

For `toffee dev check` the steps are:

1. `fmt`, once
2. `validate`, once for `dev`
3. each selected scanner, once for `dev`, in `--checks` order

For `toffee dev,prod check` the steps are:

1. `fmt`, once
2. `dev validate`, then `prod validate`
3. for each selected scanner, `dev` then `prod`

`fmt` and `validate` use the configured Terraform executable and any Terraform
global arguments, including `-chdir`.

```text
terraform [global-args] fmt -check -diff -recursive
terraform [global-args] validate
```

`validate` is the only step that sets `TF_DATA_DIR` to
`.toffee/terraform-data/<env>`. It does not receive `-var-file`.

Scanners run with the working directory set to the Terraform working directory
(the last `-chdir` directory, otherwise the current directory). Their variable
file path is relative to that directory.

```text
tflint --format compact --var-file=<env>.tfvars
checkov -d . --framework terraform --output cli --quiet --compact \
  --download-external-modules false --skip-path .terraform \
  --skip-path .toffee --var-file <env>.tfvars
```

`--quiet` and `--compact` limit Checkov to failed checks, without passing
checks and without source blocks. Toffee does not filter or rewrite scanner
output.

Toffee does not install tools, does not run `tflint --init`, and does not
download Terraform providers or Checkov external modules.

Every environment must be a valid Toffee environment before any check starts.
`check` does not compare backend state. A failed step does not skip later
steps.

## Missing tools

Selected scanners and the Terraform executable are resolved before any step
runs. A missing one stops the run before `fmt`. Nothing partial is reported as
a pass.

Checkov is a Python tool. When it is missing, print both commands:

```text
uv tool install checkov
pipx install checkov
```

TFLint is a Go binary and has no Python package. When it is missing, print its
installation page and do not print a `uv` or `pipx` command:

```text
https://github.com/terraform-linters/tflint#installation
```

When only scanners are missing, also print the Toffee command that repeats the
run without those scanners. When Terraform itself is missing, do not print that
rerun line.

Bare names are described as not found on `PATH`. A configured Terraform path
that contains a directory separator is described as not found.

## Output and exit codes

Toffee's own lines go to stderr. Terraform and scanner stdout and stderr are
inherited unchanged.

```text
Checks for dev: fmt, validate, checkov

fmt
Running: terraform fmt -check -diff -recursive
fmt passed

validate
Running: terraform validate
validate passed

checkov
Running: checkov -d . --framework terraform --output cli --quiet --compact --download-external-modules false --skip-path .terraform --skip-path .toffee --var-file vars/dev.tfvars
checkov passed

Summary
  fmt passed
  validate passed
  checkov passed
```

With more than one environment, per-environment labels include the environment
name (`dev validate`, `prod checkov`). `fmt` stays a single label. The opening
line lists environments in the order given and the check names `fmt`,
`validate`, then the selected scanners.

A step exits 0 with `<label> passed`. Any other status is
`<label> failed with exit code N`, using the tool's status.

- Exit 0 when every step exits 0.
- Exit 1 when a selected tool is missing or any step fails. The command's exit
  code is 1 even when the tool's status was something else, such as `fmt`
  exiting 3.
- Exit 2 for usage errors, including `--parallel` and a bad `--checks` value.

## Out of scope

Plan scans, OPA, Conftest, a `.toffee.json` check list, and `--parallel`
checks are not part of this command.
