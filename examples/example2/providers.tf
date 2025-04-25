terraform {
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 4.0"
    }
  }

  backend "s3" {
    # This will be configured by Toffee
  }
}

# Primary region provider
provider "aws" {
  alias  = "primary"
  region = var.primary_region
}

# Secondary region provider
provider "aws" {
  alias  = "secondary"
  region = var.secondary_region
}