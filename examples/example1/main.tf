# Example Terraform configuration
Terraform Examples with Toffee
This guide provides examples of Terraform configurations you can use with the Toffee wrapper to manage multiple environments.
Project Structure
First, let's set up a proper project structure following Toffee's conventions:
my-terraform-project/
├── main.tf             # Main Terraform configuration
├── variables.tf        # Variable definitions
├── outputs.tf          # Output definitions
├── providers.tf        # Provider configurations
└── vars/
    ├── dev.tfvars      # Variables for dev environment
    ├── dev.tfbackend   # Backend config for dev environment 
    ├── prod.tfvars     # Variables for prod environment
    ├── prod.tfbackend  # Backend config for prod environment
Example 1: Simple AWS S3 Bucket
1. Set up your Terraform files
main.tf
hclresource "aws_s3_bucket" "terraform_state" {
  bucket = "${var.project_name}-${var.environment}-state"

  tags = {
    Name        = "${var.project_name}-${var.environment}-state"
    Environment = var.environment
  }
}

resource "aws_s3_bucket_versioning" "terraform_state" {
  bucket = aws_s3_bucket.terraform_state.id
  
  versioning_configuration {
    status = "Enabled"
  }
}

resource "aws_s3_bucket_server_side_encryption_configuration" "terraform_state" {
  bucket = aws_s3_bucket.terraform_state.id

  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm = "AES256"
    }
  }
}