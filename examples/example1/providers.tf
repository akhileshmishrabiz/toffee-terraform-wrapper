terraform {
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 4.0"
    }
  }

  backend "s3" {
    # This will be configured by Toffee using the .tfbackend file
  }
}

provider "aws" {
  region = var.region
}