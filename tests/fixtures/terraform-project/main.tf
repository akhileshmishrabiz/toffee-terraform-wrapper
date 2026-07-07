terraform {
  required_version = ">= 1.0"

  backend "local" {}
}

variable "environment" {
  type        = string
  description = "Deployment environment name"
}

resource "null_resource" "example" {
  triggers = {
    environment = var.environment
  }
}

output "environment" {
  value = var.environment
}
