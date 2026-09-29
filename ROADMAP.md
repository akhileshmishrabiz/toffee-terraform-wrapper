# Roadmap

## Completed

- **Production guardrails:** Require explicit confirmation for state-changing
  commands against `prod`, `production`, and configured protected
  environments, independent of auto-approval. Verify the origin of saved plans
  and refuse environments that share state.
- **Simple environment diff:** Compare top-level variable and backend settings
  across environments while redacting sensitive values by default.

## Planned

- **Unified checks:** Provide one intuitive workflow that orchestrates
  Terraform `fmt` and `validate`, TFLint, and Checkov source scans.
- **Automation-friendly CLI:** Add machine-readable output, richer help, and
  shell completion.
- **Plan policy checks:** Support Checkov plan scans and pluggable custom policy
  enforcement, evaluating options such as OPA or Conftest without prematurely
  committing to one policy engine.
- **Optional cost estimates:** Integrate an external service such as Infracost
  for opt-in infrastructure cost estimation.

External tools will remain optional. Toffee will orchestrate established tools
rather than reimplement their analysis engines.
