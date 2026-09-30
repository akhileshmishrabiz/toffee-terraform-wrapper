"""Built-in `toffee new` template, rendered with the same tokens as custom ones."""

from typing import List, Tuple

PROVIDERS = ("aws", "google", "azurerm", "none")
BACKENDS = ("s3", "gcs", "azurerm", "local")
BACKEND_FOR_PROVIDER = {
    "aws": "s3",
    "google": "gcs",
    "azurerm": "azurerm",
    "none": "local",
}
DEFAULT_REGIONS = {"aws": "us-east-1", "google": "us-central1", "azurerm": "eastus"}
_CLOUD_FOR_BACKEND = {"s3": "aws", "gcs": "google", "azurerm": "azurerm"}
PROVIDER_VERSIONS = {"aws": "~> 6.0", "google": "~> 8.0", "azurerm": "~> 5.0"}

_REGION_DESCRIPTIONS = {
    "aws": "AWS region to deploy into.",
    "google": "Google Cloud region to deploy into.",
    "azurerm": "Azure location to deploy into.",
    "none": "Region or location, for when you add a provider.",
}

_PROVIDER_BLOCKS = {
    "aws": """\
provider "aws" {
  region = var.region

  default_tags {
    tags = {
      Project     = var.project
      Environment = var.environment
      ManagedBy   = "terraform"
    }
  }
}
""",
    "google": """\
provider "google" {
  project = var.project_id
  region  = var.region
}
""",
    "azurerm": """\
# Credentials and the subscription come from `az login` or ARM_* variables.
provider "azurerm" {
  features {}
}
""",
    "none": """\
# No provider is configured yet. Add provider blocks here, for example:
#
# provider "aws" {
#   region = var.region
# }
""",
}

_DATA_SOURCES = {
    "aws": """\
data "aws_caller_identity" "current" {}

data "aws_region" "current" {}
""",
    "google": """\
data "google_client_config" "current" {}
""",
    "azurerm": """\
data "azurerm_client_config" "current" {}
""",
    "none": """\
# Data sources read existing infrastructure, for example:
#
# data "aws_caller_identity" "current" {}
""",
}

_DATA_OUTPUTS = {
    "aws": (
        "account_id",
        "AWS account Terraform deploys into.",
        "data.aws_caller_identity.current.account_id",
    ),
    "google": (
        "project_id",
        "Google Cloud project Terraform deploys into.",
        "data.google_client_config.current.project",
    ),
    "azurerm": (
        "subscription_id",
        "Azure subscription Terraform deploys into.",
        "data.azurerm_client_config.current.subscription_id",
    ),
}

_BACKEND_SETTINGS = {
    "s3": """\
bucket  = "{{placeholder}}"
key     = "{{project}}/{{env}}/terraform.tfstate"
region  = "{{region}}"
encrypt = true
""",
    "gcs": """\
bucket = "{{placeholder}}"
prefix = "{{project}}/{{env}}"
""",
    "azurerm": """\
resource_group_name  = "{{placeholder}}"
storage_account_name = "{{placeholder}}"
container_name       = "tfstate"
key                  = "{{project}}/{{env}}/terraform.tfstate"
""",
    "local": """\
path = "state/{{env}}/terraform.tfstate"
""",
}

MAIN_TF = """\
# Root module for {{project}}. Keep reusable code in ./modules and call it
# from here with per-environment values from {{vars_dir}}/<env>.tfvars:
#
# module "app" {
#   source = "./modules/app"
#
#   project     = var.project
#   environment = var.environment
# }
"""

GITIGNORE = """\
# Terraform
.terraform/
*.tfstate
*.tfstate.*
crash.log
crash.*.log
*.tfplan
tfplan
.terraformrc
terraform.rc

# Toffee metadata and saved-plan records (<plan>.toffee.json).
# "?*" keeps the project's own .toffee.json tracked.
.toffee/
?*.toffee.json
"""

TOFFEE_JSON = """\
{
  "vars_dir": "{{vars_dir}}",
  "terraform_path": "terraform",
  "auto_approve": false
}
"""

AGENTS_MD = """\
# Working on {{project}}

This Terraform project uses [Toffee](https://github.com/akhileshmishrabiz/toffee-terraform-wrapper).
Each environment is `{{vars_dir}}/<env>.tfvars` (inputs) plus
`{{vars_dir}}/<env>.tfbackend` (state location).

- Run Terraform through Toffee: `toffee <env> plan`, never plain `terraform`.
- Before proposing a change, run `toffee <env> fmt -check -recursive`,
  `toffee <env> validate`, and `toffee <env> plan` for each affected
  environment (and `toffee <env> check` once Toffee provides it).
- Never run `apply`, `destroy`, `import`, or `state` changes against a
  protected environment (`prod`, `production`, or any listed in
  `.toffee.json`). Leave those to a human.
- Keep per-environment values in `{{vars_dir}}/`, not in `.tf` files, and give
  every environment its own state key.
- Put reusable code in `modules/` and call it from `main.tf`.
- Never commit state, plan files, `.toffee/`, or credentials.
"""


def default_region(provider: str, backend: str) -> str:
    cloud = provider if provider != "none" else _CLOUD_FOR_BACKEND.get(backend, "aws")
    return DEFAULT_REGIONS[cloud]


def builtin_files(provider: str, backend: str) -> List[Tuple[str, str]]:
    """Return (path, content) pairs in display order; paths may contain __env__."""
    return [
        ("modules/.gitkeep", ""),
        ("main.tf", MAIN_TF),
        ("outputs.tf", _outputs(provider)),
        ("variables.tf", _variables(provider)),
        ("versions.tf", _versions(provider, backend)),
        ("providers.tf", _PROVIDER_BLOCKS[provider]),
        ("data.tf", _DATA_SOURCES[provider]),
        ("vars/__env__.tfvars", _tfvars(provider)),
        ("vars/__env__.tfbackend", _tfbackend(backend)),
        (".toffee.json", TOFFEE_JSON),
        (".gitignore", GITIGNORE),
    ]


def _versions(provider: str, backend: str) -> str:
    lines = ["terraform {", '  required_version = ">= 1.5"', ""]
    if provider != "none":
        lines += [
            "  required_providers {",
            f"    {provider} = {{",
            f'      source  = "hashicorp/{provider}"',
            f'      version = "{PROVIDER_VERSIONS[provider]}"',
            "    }",
            "  }",
            "",
        ]
    lines += [
        "  # Each environment's settings are in {{vars_dir}}/<env>.tfbackend.",
        f'  backend "{backend}" {{}}',
        "}",
    ]
    return "\n".join(lines) + "\n"


def _variables(provider: str) -> str:
    variables = [
        ("project", "Project name, used in resource names and tags."),
        ("environment", "Environment name, such as dev or prod."),
        ("region", _REGION_DESCRIPTIONS[provider]),
    ]
    if provider == "google":
        variables.append(("project_id", "Google Cloud project ID to deploy into."))
    return "\n".join(
        f'variable "{name}" {{\n'
        f'  description = "{description}"\n'
        "  type        = string\n"
        "}\n"
        for name, description in variables
    )


def _outputs(provider: str) -> str:
    outputs = [("environment", "Environment this state belongs to.", "var.environment")]
    if provider in _DATA_OUTPUTS:
        outputs.append(_DATA_OUTPUTS[provider])
    return "\n".join(
        f'output "{name}" {{\n'
        f'  description = "{description}"\n'
        f"  value       = {value}\n"
        "}\n"
        for name, description, value in outputs
    )


def _tfvars(provider: str) -> str:
    if provider == "google":
        return (
            'project     = "{{project}}"\n'
            'project_id  = "{{placeholder}}"\n'
            'environment = "{{env}}"\n'
            'region      = "{{region}}"\n'
        )
    return (
        'project     = "{{project}}"\n'
        'environment = "{{env}}"\n'
        'region      = "{{region}}"\n'
    )


def _tfbackend(backend: str) -> str:
    return (
        "# Where {{env}} keeps its Terraform state. Keep it unique per environment.\n"
        + _BACKEND_SETTINGS[backend]
    )
