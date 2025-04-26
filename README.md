# Toffee

Toffee is a modern CLI tool that simplifies working with Terraform across multiple environments. It provides a clean interface for managing environment-specific configurations, reducing the complexity of Terraform commands, and streamlining your infrastructure deployment workflow.

## Why Toffee?

Managing multiple environments (development, staging, production) in Terraform traditionally requires complex command-line parameters and careful file management. Toffee solves this by:

- Automatically handling environment-specific variable files and backend configurations
- Providing simple, intuitive commands for common Terraform operations
- Managing environment configurations with dedicated commands
- Delivering rich, colorful terminal output with helpful suggestions
- Supporting project-specific and global configuration settings

## Installation

```bash
# Install from GitHub
pip install  git+https://github.com/akhileshmishrabiz/toffee-terraform-wrapper.git

```
```bash
# Upgrade
pip install --upgrade --force-reinstall git+https://github.com/akhileshmishrabiz/toffee-terraform-wrapper.git
```
```bash

# Verify installation
toffee --version
```

## Getting Started

### Project Structure

Toffee expects your project to follow this structure:

```
your-terraform-project/
├── *.tf (Terraform files)
└── vars/
    ├── dev.tfvars      # Variables for dev environment
    ├── dev.tfbackend   # Backend config for dev environment 
    ├── prod.tfvars     # Variables for prod environment
    ├── prod.tfbackend  # Backend config for prod environment
    └── ... (other environments)
```

### Creating Your First Environment

```bash
# Create a new environment
toffee env create dev

# This will generate:
# - vars/dev.tfvars
# - vars/dev.tfbackend
```

## Command Reference

### Basic Terraform Operations

```bash
# Initialize Terraform for an environment
toffee init dev

# Create an execution plan for an environment
toffee plan dev

# Apply changes for an environment
toffee apply dev

# Apply with auto-approve (no confirmation prompt)
toffee apply prod -auto-approve

# Destroy infrastructure in an environment
toffee destroy dev

# Show Terraform outputs for an environment
toffee output staging

# Refresh Terraform state
toffee refresh dev

# Format Terraform files (works with or without environment)
toffee fmt
toffee fmt dev

# Validate Terraform configuration
toffee validate dev

# Run state management commands
toffee state dev list
toffee state list  # Without environment
```

### Environment Management

```bash
# Create a new environment
toffee env create staging

# Copy an existing environment
toffee env copy dev staging

# List all available environments
toffee info envs

# Show details about a specific environment
toffee info env prod
```

### Configuration Commands

```bash
# Initialize project configuration (.toffee.json)
toffee config init

# Show current configuration
toffee config show

# Set a global configuration value
toffee config set terraform_path /usr/local/bin/terraform
toffee config set auto_approve true
toffee config set default_environment dev
```

### Information Commands

```bash
# List all available environments
toffee info envs

# Show details about a specific environment
toffee info env dev

# List available Terraform commands
toffee info commands
```

### Custom Commands

```bash
# Run any Terraform command in a specific environment
toffee run dev workspace list
toffee run prod import aws_s3_bucket.bucket bucket-name
```

## Configuration

### Project Configuration

Create a `.toffee.json` file in your project root with project-specific settings:

```json
{
  "vars_dir": "vars",
  "terraform_path": "terraform",
  "default_environment": "dev",
  "auto_approve": false
}
```

### Global Configuration

Global settings are stored in `~/.toffee/config.json`:

```json
{
  "vars_dir": "vars",
  "terraform_path": "terraform",
  "verbose": false,
  "default_environment": null,
  "auto_approve": false
}
```

## Environment Files

### Variables File (`.tfvars`)

Contains Terraform variables for a specific environment:

```hcl
# Example dev.tfvars
environment = "dev"
instance_type = "t3.micro"
region = "us-east-1"
```

### Backend Configuration (`.tfbackend`)

Contains backend configuration for a specific environment:

```hcl
# Example dev.tfbackend
bucket = "my-terraform-state"
key = "terraform/dev/terraform.tfstate"
region = "us-east-1"
encrypt = true
```

## Tips and Best Practices

1. **Use Environment Creation**: Always create environments using `toffee env create` to ensure proper file structure.

2. **Environment Naming**: Use consistent naming conventions for environments (e.g., dev, stage, prod).

3. **Project Config**: Initialize a project config with `toffee config init` to customize settings per project.

4. **Alias Common Commands**: Create shell aliases for frequently used commands:
   ```bash
   alias tp='toffee plan'
   alias ta='toffee apply'
   ```

5. **Use Auto-Approve Selectively**: Configure `auto_approve` in production environments with care.

## License

MIT