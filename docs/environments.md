---
title: Environments
description: How Toffee isolates Terraform environment inputs, state, and local metadata.
---

# Environments

Each environment is a complete pair:

```text
vars/
├── dev.tfvars
├── dev.tfbackend
├── prod.tfvars
└── prod.tfbackend
```

The `.tfvars` file contains Terraform inputs. The `.tfbackend` file contains
backend settings, including a state destination unique to that environment.

```hcl
# vars/dev.tfvars
environment = "dev"
region      = "us-east-1"
```

```hcl
# vars/dev.tfbackend
bucket  = "company-tf-state"
key     = "service/dev/terraform.tfstate"
region  = "us-east-1"
encrypt = true
```

Toffee also sets a separate local data directory:

```text
.toffee/terraform-data/dev/
.toffee/terraform-data/prod/
```

That prevents one target's `init` from replacing another target's local
backend metadata. It does not replace backend isolation: every environment
must still resolve to distinct state.

## Add an environment

```bash
toffee env create staging
toffee env copy staging prod
toffee info envs
```

After creating or copying, review both files and make the backend state
destination unique. Toffee refuses state-reading and state-changing commands
if two environments share state or resolve to each other's files.

## Compare environments

Use `toffee diff dev prod` before planning to inspect configuration drift.
The comparison is local, top-level, and redacts sensitive-looking values by
default. It does not evaluate Terraform expressions or compare plans.
