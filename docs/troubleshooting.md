---
title: Troubleshooting
description: Resolve common Toffee setup, environment, and plan safety errors.
---

# Troubleshooting

## `Replace CHANGE-ME ... before running init`

Edit the named `.tfbackend` file and replace `CHANGE-ME` with the real backend
value. A command-line `-backend-config=key=value` can supply that setting, but
committed environment configuration is usually clearer.

## Environment files are incomplete

Every environment needs both `vars/<name>.tfvars` and
`vars/<name>.tfbackend`. Restore the missing file or recreate the pair with
`toffee env create <name>`.

## Environments resolve to shared state

Change the backend `key`, `path`, or equivalent state identity so every
environment is unique. Toffee intentionally refuses state-reading and
state-changing commands in this condition.

## A saved plan cannot be verified

Keep the plan and its `.toffee.json` sidecar together. A sidecar signed on
another machine cannot be authenticated with this user's local key, so Toffee
requires confirmation. Recreate the plan locally for a verified record:

```bash
toffee dev plan -out=tfplan
toffee dev apply tfplan
```

Changed plans and plans recorded for another environment are refused.

## Terraform is not found

Confirm Terraform 1.5 or newer is on `PATH`, or set a trusted executable:

```bash
export TOFFEE_TERRAFORM_PATH=/opt/terraform/bin/terraform
toffee info version
```

Explicit paths belong in the environment variable or global config, not a
project `.toffee.json`.

## Parallel execution is rejected

Interactive operations cannot run in parallel. Parallel apply and destroy
require `-auto-approve`; `init` is always serialized. Remove `--parallel` when
you need prompts.

Still stuck? [Open an issue](https://github.com/akhileshmishrabiz/toffee-terraform-wrapper/issues)
with the command, sanitized output, Toffee version, and Terraform version.
