---
title: Configuration
description: Toffee configuration keys, defaults, precedence, and executable trust rules.
---

# Configuration

Project settings live in `.toffee.json`; global settings live in
`~/.toffee/config.json`.

| Key | Type | Default | Purpose |
| --- | --- | --- | --- |
| `vars_dir` | non-empty string | `"vars"` | Directory holding paired environment files |
| `terraform_path` | non-empty string | `"terraform"` | Terraform-compatible executable |
| `verbose` | boolean | `false` | Additional wrapper output |
| `auto_approve` | boolean | `false` | Add approval where Toffee allows it |
| `protected_environments` | list of names | `[]` | Additional protected environment names |

```json
{
  "vars_dir": "vars",
  "terraform_path": "terraform",
  "auto_approve": false,
  "verbose": false,
  "protected_environments": ["critical"]
}
```

## Precedence

Values resolve from lowest to highest priority:

1. built-in defaults;
2. global configuration;
3. project configuration;
4. `TOFFEE_TERRAFORM_PATH` for the executable.

Global and project `protected_environments` are combined, so a project cannot
remove a globally protected name.

## Trust rules

Project files are untrusted. A project `terraform_path` may name only
`terraform`, `tofu`, or `opentofu`, optionally with a version suffix such as
`terraform1.9`; it must resolve on `PATH`. Put explicit paths or other
executable names in global configuration or `TOFFEE_TERRAFORM_PATH`.

A project `vars_dir` must be relative and remain inside the project, including
after symlink resolution. Unknown keys and incorrectly typed values are
errors.

## Manage settings

```bash
toffee config show
toffee config init
toffee config set verbose true
```

`config set` writes globally unless `--project` is supplied.
List-valued `protected_environments` must be edited directly in the JSON file;
`config set` deliberately refuses list settings.
