# Toffee

A modern CLI tool for deploying Terraform across multiple environments.

## Features

- **Simplified Workflow**: Run Terraform commands for specific environments with a clean syntax
- **Environment Management**: Automatic handling of `.tfvars` and `.tfbackend` files
- **Smart Error Messages**: Helpful suggestions when environment names are mistyped
- **Rich Output**: Colorful, well-formatted terminal output
- **Configuration System**: Global and project-specific configuration options
- **Environment Discovery**: Automatic discovery of available environments
- **Command Extensions**: Support for all Terraform commands with proper arg passing
- **Information Commands**: View environment details and configuration

## Installation

```bash
# From GitHub
pip install git+https://github.com/akhileshmishrabiz/toffee-terraform-wrapper.git

```

## Basic Usage

```bash
# Initialize Terraform in the dev environment
toffee init dev

# Plan changes for production
toffee plan prod

# Apply changes to staging with auto-approve
toffee apply stage -auto-approve

# Destroy resources in dev (with confirmation prompt)
toffee destroy dev
```

## Advanced Usage

### Custom Terraform Commands

```bash
# Run any Terraform command
toffee run dev state list
toffee run prod workspace list
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

### Configuration

```bash
# Show current configuration
toffee config show

# Set global configuration values
toffee config set default_environment dev
toffee config set auto_approve true

# Initialize project configuration
toffee config init
```

## File Structure

Toffee expects your project to have a specific file structure:

```
project_root/
├── *.tf (Terraform files)
└── vars/
    ├── dev.tfvars      # Variables for dev environment
    ├── dev.tfbackend   # Backend config for dev environment 
    ├── prod.tfvars     # Variables for prod environment
    ├── prod.tfbackend  # Backend config for prod environment
    └── ... (other environments)
```

## Project Configuration

You can create a `.toffee.json` file in your project root to configure project-specific settings:

```json
{
  "vars_dir": "vars",
  "terraform_path": "terraform",
  "default_environment": "dev",
  "auto_approve": false
}
```

## Global Configuration

Global configuration is stored in `~/.toffee/config.json`:

```json
{
  "vars_dir": "vars",
  "terraform_path": "terraform",
  "verbose": false,
  "default_environment": null,
  "auto_approve": false
}
```

## License

MIT