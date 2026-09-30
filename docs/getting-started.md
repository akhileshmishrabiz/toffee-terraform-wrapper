---
title: Getting started
description: Install Toffee from GitHub and create or adopt a Terraform project.
---

# Getting started

## Requirements

- Python 3.10 or newer
- Terraform 1.5 or newer

OpenTofu can be selected as the executable, but it is not claimed as tested for
Toffee 1.0.0.

## Install from GitHub

Toffee is not published on PyPI. Install the GitHub repository as an isolated
command.

=== "pipx"

    ```bash
    pipx install git+https://github.com/akhileshmishrabiz/toffee-terraform-wrapper.git
    toffee --version
    ```

=== "uv"

    ```bash
    uv tool install git+https://github.com/akhileshmishrabiz/toffee-terraform-wrapper.git
    toffee --version
    ```

## Create your first project

```bash
toffee new service
cd service
```

`toffee new [DIRECTORY]` has no configuration options beyond `--help`. It
always creates a compact AWS project using an S3 backend, `us-east-1`, and a
single `dev` environment. With no directory, it scaffolds the current
directory. Existing files are never overwritten.

Open `vars/dev.tfbackend` and replace `CHANGE-ME` with your S3 state bucket.
Toffee blocks `init` while the placeholder remains. Configure AWS credentials
through the normal AWS credential chain—never in Toffee or Terraform files.

```bash
toffee dev init
toffee dev validate
toffee dev plan
toffee dev apply
```

## Adopt an existing project

Run `toffee new` in an existing Terraform root. When `.tf` files already
exist, Toffee adds only `.toffee.json`, `.gitignore` entries, and the
`vars/dev.tfvars` / `vars/dev.tfbackend` pair.

Your root module needs a partial backend block:

```hcl
terraform {
  required_version = ">= 1.5"
  backend "s3" {}
}
```

Review the generated environment files, replace `CHANGE-ME`, and keep every
environment's state destination unique.
