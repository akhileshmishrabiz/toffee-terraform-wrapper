"""Plan and safely write the fixed `toffee new` scaffold."""

import fnmatch
import os
import re
import stat
import tempfile
from dataclasses import dataclass, field
from typing import List, Optional

from .config import PROJECT_CONFIG_NAME
from .text import printable

CREATE = "create"
APPEND = "append"
SKIP = "skip"
PROJECT_NAME = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]*")


class ScaffoldError(ValueError):
    """Raised when the scaffold cannot be created safely."""


@dataclass
class FileChange:
    path: str
    action: str
    content: bytes = b""
    mode: Optional[int] = None
    added_lines: int = 0


@dataclass
class Plan:
    root: str
    project: str
    changes: List[FileChange]
    omitted: List[str] = field(default_factory=list)

    def with_action(self, action: str) -> List[FileChange]:
        return [change for change in self.changes if change.action == action]

    def full_path(self, path: str) -> str:
        return os.path.join(self.root, *path.split("/"))


def plan_project(directory: Optional[str] = None) -> Plan:
    """Decide what the fixed scaffold would create without writing anything."""
    root = os.path.abspath(directory or ".")
    if os.path.lexists(root) and not os.path.isdir(root):
        raise ScaffoldError(f"{printable(directory)} exists and is not a directory.")

    project = _project_name(root)
    existing_terraform = _has_terraform(root)
    root_real = os.path.realpath(root)
    changes = []
    omitted = []
    for path, content in _files(project):
        if existing_terraform and _is_terraform_file(path):
            target = os.path.join(root, *path.split("/"))
            if not os.path.lexists(target):
                omitted.append(path)
                continue
        changes.append(_classify(root, root_real, path, content.encode("utf-8")))
    return Plan(root, project, changes, omitted)


def write_plan(plan: Plan) -> None:
    """Stage all changes, then install them without overwriting existing files."""
    root_real = os.path.realpath(plan.root)
    umask = _umask()
    staged = []
    try:
        for change in plan.changes:
            if change.action == SKIP:
                continue
            target = plan.full_path(change.path)
            directory = os.path.dirname(target)
            os.makedirs(directory, exist_ok=True)
            _check_writable(plan.root, root_real, change.path)
            handle, temporary = tempfile.mkstemp(
                dir=directory, prefix=".toffee-new-", suffix=".tmp"
            )
            staged.append((change, temporary, target))
            with os.fdopen(handle, "wb") as staged_file:
                staged_file.write(change.content)
            mode = change.mode if change.mode is not None else 0o666 & ~umask
            os.chmod(temporary, mode)
        for change, temporary, target in staged:
            if change.action == APPEND:
                os.replace(temporary, target)
            else:
                _link_new(temporary, target, change.path)
    finally:
        for _change, temporary, _target in staged:
            if os.path.lexists(temporary):
                os.remove(temporary)


def _project_name(root: str) -> str:
    name = os.path.basename(root)
    if not PROJECT_NAME.fullmatch(name):
        raise ScaffoldError(
            "The target directory name must start with a letter or digit and contain "
            "only letters, digits, '.', '_', and '-'."
        )
    return name


def _has_terraform(root: str) -> bool:
    if not os.path.isdir(root):
        return False
    return any(name.endswith((".tf", ".tf.json")) for name in os.listdir(root))


def _is_terraform_file(path: str) -> bool:
    return path.endswith((".tf", ".tf.json")) or path.startswith("modules/")


def _files(project: str):
    files = [
        ("modules/.gitkeep", ""),
        (
            "main.tf",
            "# Add reusable modules here, for example:\n"
            '# module "service" {\n'
            '#   source = "./modules/service"\n'
            "#\n"
            "#   project     = var.project\n"
            "#   environment = var.environment\n"
            "# }\n",
        ),
        (
            "outputs.tf",
            'output "environment" {\n'
            '  description = "Environment this state belongs to."\n'
            "  value       = var.environment\n"
            "}\n",
        ),
        (
            "variables.tf",
            'variable "project" {\n'
            '  description = "Project name used in tags."\n'
            "  type        = string\n"
            "}\n\n"
            'variable "environment" {\n'
            '  description = "Environment name."\n'
            "  type        = string\n"
            "}\n\n"
            'variable "region" {\n'
            '  description = "AWS region."\n'
            "  type        = string\n"
            "}\n",
        ),
        (
            "versions.tf",
            "terraform {\n"
            '  required_version = ">= 1.5"\n\n'
            "  required_providers {\n"
            "    aws = {\n"
            '      source  = "hashicorp/aws"\n'
            '      version = "~> 6.0"\n'
            "    }\n"
            "  }\n\n"
            '  backend "s3" {}\n'
            "}\n",
        ),
        (
            "providers.tf",
            'provider "aws" {\n'
            "  region = var.region\n\n"
            "  default_tags {\n"
            "    tags = {\n"
            "      Project     = var.project\n"
            "      Environment = var.environment\n"
            '      ManagedBy   = "terraform"\n'
            "    }\n"
            "  }\n"
            "}\n",
        ),
        (
            "data.tf",
            'data "aws_caller_identity" "current" {}\n\n'
            'data "aws_region" "current" {}\n',
        ),
        (
            "vars/dev.tfvars",
            f'project     = "{project}"\n'
            'environment = "dev"\n'
            'region      = "us-east-1"\n',
        ),
        (
            "vars/dev.tfbackend",
            "# Keep this state key unique per environment.\n"
            'bucket  = "CHANGE-ME"\n'
            f'key     = "{project}/dev/terraform.tfstate"\n'
            'region  = "us-east-1"\n'
            "encrypt = true\n",
        ),
        (
            ".toffee.json",
            '{\n  "vars_dir": "vars",\n  "terraform_path": "terraform",\n'
            '  "auto_approve": false\n}\n',
        ),
        (
            ".gitignore",
            "# Terraform\n"
            ".terraform/\n"
            "*.tfstate\n"
            "*.tfstate.*\n"
            "crash.log\n"
            "crash.*.log\n"
            "*.tfplan\n"
            "tfplan\n"
            ".terraformrc\n"
            "terraform.rc\n\n"
            "# Toffee metadata and saved-plan records.\n"
            ".toffee/\n"
            "?*.toffee.json\n",
        ),
    ]
    return files


def _classify(root: str, root_real: str, path: str, content: bytes) -> FileChange:
    target = os.path.join(root, *path.split("/"))
    if path == ".gitignore" and os.path.lexists(target):
        _check_writable(root, root_real, path)
        return _gitignore_change(target, content)
    if os.path.lexists(target):
        if os.path.isdir(target) and not os.path.islink(target):
            raise ScaffoldError(f"{path} exists and is a directory.")
        return FileChange(path, SKIP)
    _check_writable(root, root_real, path)
    return FileChange(path, CREATE, content)


def _check_writable(root: str, root_real: str, path: str) -> None:
    current = root
    for part in path.split("/"):
        current = os.path.join(current, part)
        if os.path.islink(current):
            raise ScaffoldError(
                f"Refusing to write through symlink: {printable(path)}."
            )
    parent = os.path.dirname(current)
    if os.path.lexists(parent) and not os.path.isdir(parent):
        raise ScaffoldError(f"{printable(path)}: a parent path is not a directory.")
    if os.path.commonpath([os.path.realpath(current), root_real]) != root_real:
        raise ScaffoldError(
            f"Refusing to write outside the project: {printable(path)}."
        )


def _gitignore_change(target: str, template_content: bytes) -> FileChange:
    try:
        with open(target, "rb") as gitignore:
            existing = gitignore.read().decode("utf-8")
    except UnicodeDecodeError:
        return FileChange(".gitignore", SKIP)
    present = {line.strip() for line in existing.splitlines()}
    wanted = [
        line.strip()
        for line in template_content.decode().splitlines()
        if line.strip() and not line.startswith("#")
    ]
    missing = [line for line in dict.fromkeys(wanted) if line not in present]
    if _ignores_project_config(existing.splitlines() + missing):
        missing.append(f"!/{PROJECT_CONFIG_NAME}")
    if not missing:
        return FileChange(".gitignore", SKIP)
    separator = "\n" if existing and not existing.endswith("\n") else ""
    spacer = "\n" if existing.strip() else ""
    content = (
        existing
        + separator
        + spacer
        + "# Added by toffee new\n"
        + "\n".join(missing)
        + "\n"
    )
    return FileChange(
        ".gitignore",
        APPEND,
        content.encode(),
        stat.S_IMODE(os.stat(target).st_mode),
        len(missing),
    )


def _ignores_project_config(lines: List[str]) -> bool:
    ignored = False
    for line in lines:
        pattern = line.strip()
        if not pattern or pattern.startswith("#") or pattern.endswith("/"):
            continue
        negated = pattern.startswith("!")
        pattern = pattern[1:] if negated else pattern
        pattern = pattern.removeprefix("**/").lstrip("/")
        if "/" not in pattern and fnmatch.fnmatchcase(PROJECT_CONFIG_NAME, pattern):
            ignored = not negated
    return ignored


def _link_new(temporary: str, target: str, path: str) -> None:
    try:
        os.link(temporary, target)
    except FileExistsError:
        raise ScaffoldError(
            f"{printable(path)} appeared while writing; it was not overwritten."
        ) from None
    except OSError:
        descriptor = None
        created = False
        try:
            descriptor = os.open(target, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            created = True
            with (
                open(temporary, "rb") as source,
                os.fdopen(descriptor, "wb") as destination,
            ):
                descriptor = None
                while chunk := source.read(1024 * 1024):
                    destination.write(chunk)
            os.chmod(target, stat.S_IMODE(os.stat(temporary).st_mode))
        except FileExistsError:
            raise ScaffoldError(
                f"{printable(path)} appeared while writing; it was not overwritten."
            ) from None
        except BaseException:
            if descriptor is not None:
                os.close(descriptor)
            if created:
                try:
                    os.remove(target)
                except OSError:
                    pass
            raise


def _umask() -> int:
    mask = os.umask(0)
    os.umask(mask)
    return mask
