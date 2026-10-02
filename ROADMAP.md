# Roadmap

## Completed

- **1.0 GA (2026-09-30):** Audited and verified the environment-first wrapper,
  production guardrails, state isolation, signed saved-plan records, parallel
  execution, configuration, project scaffolding, environment diff, packaging,
  documentation, and supported Python matrix for the 1.0.0 release.
- **Production guardrails:** Require explicit confirmation for state-changing
  commands against `prod`, `production`, and configured protected
  environments, independent of auto-approval. Verify the origin of saved plans
  and refuse environments that share state.
- **Simple environment diff:** Compare top-level variable and backend settings
  across environments while redacting sensitive values by default, with an
  `--exit-code` option for scripts.
- **Project scaffolding:** `toffee new` writes one minimal built-in template
  (`versions.tf`, `main.tf`, `variables.tf`, `outputs.tf`, `providers.tf`,
  `data.tf`, `modules/`, `vars/dev.tfvars`, `vars/dev.tfbackend` with a unique
  state key, `.toffee.json`, and `.gitignore`). The scaffold intentionally has
  fixed AWS, S3, `us-east-1`, and `dev` defaults and no configuration options.
  It never overwrites existing files.
- **Unified checks:** `toffee <env> check` runs Terraform `fmt` and `validate`,
  and runs TFLint and Checkov source scans when they are named with
  `--checks`. Checkov reports failed checks only. Plan scans remain separate.

## Planned

- **Automation-friendly CLI:** Add stable Toffee-owned machine-readable output
  and richer structured help. Click shell completion for current Toffee
  commands is documented; dynamic environment and Terraform completion remains
  planned.
- **Plan policy checks:** Support Checkov plan scans and pluggable custom policy
  enforcement, evaluating options such as OPA or Conftest without prematurely
  committing to one policy engine.
- **Optional cost estimates:** Integrate an external service such as Infracost
  for opt-in infrastructure cost estimation.
- **AI-agent interface:** Provide stable `--json` output and documented exit
  codes for plan, check, diff, and cost, plus an MCP server (`toffee mcp`)
  exposing read, plan, and check tools. It will never apply to protected
  environments.
- **Plan risk summary:** Show a deterministic summary of a plan in the
  protected-environment prompt: change counts, deletions and replacements, and
  IAM or network exposure changes.
- **Optional Jev assessment:** Add an opt-in assessment, for example
  `check --plan --assess`, that sends a redacted plan summary to the Jev
  (TypeSafe AI) typed decision model through a configurable endpoint such as
  OpenRouter or Vercel AI Gateway, and reports whether the plan matches the
  stated intent along with a risk rating. It will be strictly advisory: it
  may add warnings or confirmations but never skip protections. It will be
  off by default and require no SDK.

External tools will remain optional. Toffee will orchestrate established tools
rather than reimplement their analysis engines.
