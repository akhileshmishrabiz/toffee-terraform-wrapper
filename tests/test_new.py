"""Focused tests for the fixed `toffee new` scaffold."""

import os
import shutil
import stat
import subprocess
from pathlib import Path

import pytest
from click.testing import CliRunner

from toffee.cli import app
from toffee.core import scaffold
from toffee.core.backend import read_settings

MOCK_TERRAFORM = Path(__file__).parent / "fixtures/mock_terraform.sh"

DEFAULT_FILES = [
    ".gitignore",
    ".toffee.json",
    "data.tf",
    "main.tf",
    "modules/.gitkeep",
    "outputs.tf",
    "providers.tf",
    "variables.tf",
    "vars/dev.tfbackend",
    "vars/dev.tfvars",
    "versions.tf",
]

GOLDEN_OUTPUT = """\
Created 11 files for project service:

service/
├── modules/
│   └── .gitkeep
├── main.tf
├── outputs.tf
├── variables.tf
├── versions.tf
├── providers.tf
├── data.tf
├── vars/
│   ├── dev.tfvars
│   └── dev.tfbackend
├── .toffee.json
└── .gitignore

Next steps:
  1. Replace CHANGE-ME in service/vars/dev.tfbackend (bucket)
  2. cd service && toffee dev init
  3. toffee dev plan
"""


@pytest.fixture
def work(tmp_path, monkeypatch):
    root = tmp_path / "work"
    root.mkdir()
    monkeypatch.chdir(root)
    return root


def toffee(*args, env=None):
    return CliRunner().invoke(app, list(args), env=env)


def files_under(root):
    return sorted(
        os.path.relpath(os.path.join(current, name), root).replace(os.sep, "/")
        for current, _dirs, names in os.walk(root)
        for name in names
    )


def assert_clean_error(result):
    assert result.exit_code != 0
    assert result.stdout == ""
    assert result.stderr.startswith("Error:")
    assert "Traceback" not in result.output


def test_directory_form_creates_exact_fixed_tree_and_output(work):
    result = toffee("new", "service")

    assert result.exit_code == 0, result.output
    assert result.stderr == ""
    assert result.stdout == GOLDEN_OUTPUT
    assert "\x1b" not in result.output
    assert files_under(work / "service") == DEFAULT_FILES


def test_current_directory_form_uses_basename(work):
    result = toffee("new")

    assert result.exit_code == 0, result.output
    assert 'project     = "work"' in (work / "vars/dev.tfvars").read_text()
    assert result.stdout.startswith("Created 11 files for project work:")


def test_fixed_aws_s3_dev_contents(work):
    toffee("new", "service")
    root = work / "service"

    assert 'required_version = ">= 1.5"' in (root / "versions.tf").read_text()
    assert 'source  = "hashicorp/aws"' in (root / "versions.tf").read_text()
    assert 'version = "~> 6.0"' in (root / "versions.tf").read_text()
    assert 'backend "s3" {}' in (root / "versions.tf").read_text()
    assert (root / "vars/dev.tfvars").read_text() == (
        'project     = "service"\nenvironment = "dev"\nregion      = "us-east-1"\n'
    )
    assert read_settings(str(root / "vars/dev.tfbackend")) == {
        "bucket": "CHANGE-ME",
        "key": "service/dev/terraform.tfstate",
        "region": "us-east-1",
        "encrypt": "true",
    }
    for name in ("project", "environment", "region"):
        assert f'variable "{name}"' in (root / "variables.tf").read_text()
    assert "default_tags" in (root / "providers.tf").read_text()
    assert 'data "aws_caller_identity" "current" {}' in (root / "data.tf").read_text()
    assert 'data "aws_region" "current" {}' in (root / "data.tf").read_text()
    assert 'output "environment"' in (root / "outputs.tf").read_text()
    assert 'module "service"' in (root / "main.tf").read_text()
    text = "".join(
        (root / path).read_text()
        for path in DEFAULT_FILES
        if not path.endswith(".gitkeep")
    ).lower()
    for credential in ("access_key", "secret_key", "client_secret", "sas_token"):
        assert credential not in text


def test_help_has_only_directory_and_help():
    result = toffee("new", "--help")

    assert result.exit_code == 0
    assert "Usage: app new [OPTIONS] [DIRECTORY]" in result.stdout
    assert "DIRECTORY defaults to the current directory." in result.stdout
    assert result.stdout.count("toffee new service") == 1
    assert result.stdout.count("toffee new\n") == 1
    assert result.stdout.count("--help") == 1
    for removed in (
        "--name",
        "--envs",
        "--provider",
        "--backend",
        "--region",
        "--dry-run",
        "--agents",
        "--template",
    ):
        assert removed not in result.stdout
    top = toffee("--help")
    assert "new     Create a minimal Terraform project for Toffee." in top.stdout


@pytest.mark.parametrize(
    "option",
    [
        "--name",
        "--envs",
        "--provider",
        "--backend",
        "--region",
        "--dry-run",
        "--agents",
        "--template",
    ],
)
def test_removed_options_fail_and_write_nothing(work, option):
    result = toffee("new", "service", option)

    assert result.exit_code == 2
    assert f"No such option '{option}'" in result.stderr
    assert os.listdir(work) == []


def test_rerun_never_overwrites_and_reports_nothing(work):
    toffee("new")
    (work / "main.tf").write_text("# mine\n")
    before = {path: (work / path).read_bytes() for path in files_under(work)}

    result = toffee("new")

    assert result.stdout == "Nothing to create; all files already exist in ./.\n"
    assert {path: (work / path).read_bytes() for path in files_under(work)} == before


def test_existing_terraform_project_gets_only_toffee_files(work):
    (work / "main.tf").write_text("# existing\n")

    result = toffee("new")

    assert result.exit_code == 0, result.output
    assert (work / "main.tf").read_text() == "# existing\n"
    assert not (work / "modules").exists()
    assert not (work / "versions.tf").exists()
    assert (work / "vars/dev.tfvars").is_file()
    assert (work / "vars/dev.tfbackend").is_file()
    assert (work / ".toffee.json").is_file()
    assert (work / ".gitignore").is_file()
    assert "no .tf files were added" in result.stdout


def test_gitignore_appends_only_missing_lines(work):
    (work / ".gitignore").write_text("node_modules/\n.terraform/")

    toffee("new")
    text = (work / ".gitignore").read_text()
    assert text.startswith("node_modules/\n.terraform/\n\n# Added by toffee new\n")
    assert text.count(".terraform/") == 1
    assert "?*.toffee.json" in text
    before = text
    toffee("new")
    assert (work / ".gitignore").read_text() == before


def test_refuses_to_write_through_symlink(work, tmp_path):
    outside = tmp_path / "outside"
    outside.mkdir()
    (work / "vars").symlink_to(outside, target_is_directory=True)

    result = toffee("new")

    assert_clean_error(result)
    assert "Refusing to write through symlink: vars/dev.tfvars" in result.stderr
    assert os.listdir(outside) == []


def test_existing_symlinked_file_is_skipped(work, tmp_path):
    outside = tmp_path / "main.tf"
    outside.write_text("# shared\n")
    (work / "main.tf").symlink_to(outside)

    result = toffee("new")

    assert result.exit_code == 0, result.output
    assert outside.read_text() == "# shared\n"


def test_atomic_write_race_does_not_overwrite(work, monkeypatch):
    original = scaffold._link_new

    def race(temporary, target, path):
        if path == "main.tf":
            with open(target, "w", encoding="utf-8") as competing:
                competing.write("# competitor\n")
        original(temporary, target, path)

    monkeypatch.setattr(scaffold, "_link_new", race)
    result = toffee("new")

    assert_clean_error(result)
    assert "appeared while writing" in result.stderr
    assert (work / "main.tf").read_text() == "# competitor\n"


def test_init_stops_at_change_me(work, tmp_path, mock_terraform_log):
    mock = tmp_path / "mock_terraform.sh"
    shutil.copy2(MOCK_TERRAFORM, mock)
    mock.chmod(mock.stat().st_mode | stat.S_IXUSR)
    toffee("new")

    result = toffee(
        "dev",
        "init",
        env={
            "TOFFEE_TERRAFORM_PATH": str(mock),
            "MOCK_TF_LOG": str(mock_terraform_log),
        },
    )

    assert result.exit_code == 1
    assert "Replace CHANGE-ME in vars/dev.tfbackend (bucket)" in result.stderr
    assert mock_terraform_log.read_text() == ""


@pytest.mark.skipif(shutil.which("terraform") is None, reason="terraform not installed")
def test_real_terraform_fmt_and_syntax(work):
    toffee("new")

    formatted = subprocess.run(
        ["terraform", "fmt", "-check", "-recursive"],
        cwd=work,
        text=True,
        capture_output=True,
        check=False,
    )

    assert formatted.returncode == 0, formatted.stdout + formatted.stderr
