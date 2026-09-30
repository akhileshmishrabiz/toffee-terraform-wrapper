"""Tests for `toffee new` project scaffolding and its user experience."""

import json
import os
import re
import shlex
import shutil
import stat
import subprocess
from pathlib import Path

import pytest
from click.testing import CliRunner

from tests.conftest import MOCK_TERRAFORM
from toffee.cli import app
from toffee.commands.base import BaseCommand
from toffee.core.backend import read_settings
from toffee.core.config import Config, read_config_file
from toffee.core.placeholders import PLACEHOLDER

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

GOLDEN_DEFAULT_OUTPUT = """\
Created 11 files for project my-service:

my-service/
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
  1. Replace CHANGE-ME in my-service/vars/dev.tfbackend (bucket)
  2. cd my-service && toffee dev init
  3. toffee dev plan
"""

STEP = re.compile(r"^  (\d)\. (.+)$")


@pytest.fixture
def work(tmp_path, monkeypatch):
    directory = tmp_path / "work"
    directory.mkdir()
    monkeypatch.chdir(directory)
    return directory


@pytest.fixture
def mock_env(tmp_path, mock_terraform_log):
    mock = tmp_path / "mock_terraform.sh"
    shutil.copy2(MOCK_TERRAFORM, mock)
    mock.chmod(mock.stat().st_mode | stat.S_IXUSR)
    return {"TOFFEE_TERRAFORM_PATH": str(mock), "MOCK_TF_LOG": str(mock_terraform_log)}


def toffee(*args, env=None, input=None):
    return CliRunner().invoke(app, list(args), env=env, input=input)


def files_under(root):
    return sorted(
        os.path.relpath(os.path.join(current, name), root).replace(os.sep, "/")
        for current, _dirs, names in os.walk(root)
        for name in names
    )


def next_steps(stdout):
    lines = stdout.split("Next steps:\n", 1)[1].splitlines()
    return [STEP.match(line).group(2) for line in lines if STEP.match(line)]


def run_step(step, env):
    """Run a printed step as a user would paste it; a cd persists like a shell's."""
    command = step
    if step.startswith("cd "):
        directory, command = step[3:].split(" && ", 1)
        os.chdir(shlex.split(directory)[0])
    argv = shlex.split(command)
    assert argv[0] == "toffee"
    return toffee(*argv[1:], env=env)


def assert_one_line_error(result):
    assert result.exit_code == 1
    assert result.stdout == ""
    assert result.stderr.startswith("Error: ")
    assert result.stderr.count("\n") == 1
    assert "Traceback" not in result.output


class TestDefaultScaffold:
    def test_zero_flags_creates_the_standard_layout(self, work):
        result = toffee("new")

        assert result.exit_code == 0, result.output
        assert result.stderr == ""
        assert files_under(work) == DEFAULT_FILES
        assert (work / "modules").is_dir()

    def test_project_name_comes_from_the_directory(self, work):
        toffee("new", "billing-api")

        tfvars = (work / "billing-api" / "vars" / "dev.tfvars").read_text()
        assert 'project     = "billing-api"' in tfvars
        backend = read_settings(str(work / "billing-api" / "vars" / "dev.tfbackend"))
        assert backend["key"] == "billing-api/dev/terraform.tfstate"

    def test_name_option_overrides_the_directory(self, work):
        toffee("new", "x", "--name", "payments")

        assert 'project     = "payments"' in (work / "x/vars/dev.tfvars").read_text()

    def test_aws_contents(self, work):
        toffee("new", "svc")
        root = work / "svc"

        versions = (root / "versions.tf").read_text()
        assert 'required_version = ">= 1.5"' in versions
        assert 'source  = "hashicorp/aws"' in versions
        assert 'version = "~> 6.0"' in versions
        assert 'backend "s3" {}' in versions
        variables = (root / "variables.tf").read_text()
        for name in ("project", "environment", "region"):
            assert f'variable "{name}"' in variables
        providers = (root / "providers.tf").read_text()
        assert "region = var.region" in providers
        assert "default_tags" in providers
        assert "Environment = var.environment" in providers
        data = (root / "data.tf").read_text()
        assert 'data "aws_caller_identity" "current" {}' in data
        assert 'data "aws_region" "current" {}' in data
        outputs = (root / "outputs.tf").read_text()
        assert 'output "environment"' in outputs
        assert "data.aws_caller_identity.current.account_id" in outputs
        assert 'module "app"' in (root / "main.tf").read_text()
        assert (root / "vars/dev.tfvars").read_text() == (
            'project     = "svc"\nenvironment = "dev"\nregion      = "us-east-1"\n'
        )
        backend = read_settings(str(root / "vars/dev.tfbackend"))
        assert backend == {
            "bucket": PLACEHOLDER,
            "key": "svc/dev/terraform.tfstate",
            "region": "us-east-1",
            "encrypt": "true",
        }

    def test_generated_config_passes_validation_and_keeps_prod_protected(self, work):
        toffee("new", "svc", "--envs", "dev,prod")

        path = work / "svc" / ".toffee.json"
        assert read_config_file(str(path)) == {
            "vars_dir": "vars",
            "terraform_path": "terraform",
            "auto_approve": False,
        }
        merged = Config().get_project_config(str(work / "svc"))
        assert merged["auto_approve"] is False
        os.chdir(work / "svc")
        assert BaseCommand().is_protected("prod")

    def test_google_asks_for_the_project_id_with_the_same_marker(self, work):
        result = toffee("new", "g", "--provider", "google")

        assert result.exit_code == 0, result.output
        root = work / "g"
        assert 'variable "project_id"' in (root / "variables.tf").read_text()
        assert 'project_id  = "CHANGE-ME"' in (root / "vars/dev.tfvars").read_text()
        assert 'region      = "us-central1"' in (root / "vars/dev.tfvars").read_text()
        assert 'backend "gcs" {}' in (root / "versions.tf").read_text()
        assert next_steps(result.stdout)[0] == (
            "Replace CHANGE-ME in g/vars/dev.tfbackend (bucket) and "
            "g/vars/dev.tfvars (project_id)"
        )

    def test_provider_none_needs_no_edits(self, work):
        result = toffee("new", "--provider", "none")

        assert result.exit_code == 0, result.output
        assert 'backend "local" {}' in (work / "versions.tf").read_text()
        assert "required_providers" not in (work / "versions.tf").read_text()
        assert all(
            line.startswith("#") or not line
            for line in (work / "data.tf").read_text().splitlines()
        )
        assert PLACEHOLDER not in result.stdout
        assert next_steps(result.stdout) == ["toffee dev init", "toffee dev plan"]

    @pytest.mark.parametrize(
        "provider, backend, region",
        [
            ("aws", "s3", "us-east-1"),
            ("google", "gcs", "us-central1"),
            ("azurerm", "azurerm", "eastus"),
            ("none", "local", "us-east-1"),
        ],
    )
    def test_backend_and_region_are_inferred_from_the_provider(
        self, work, provider, backend, region
    ):
        toffee("new", "--provider", provider)

        assert f'backend "{backend}" {{}}' in (work / "versions.tf").read_text()
        assert f'region      = "{region}"' in (work / "vars/dev.tfvars").read_text()

    def test_agents_file_is_opt_in(self, work):
        toffee("new", "a")
        toffee("new", "b", "--agents")

        assert not (work / "a" / "AGENTS.md").exists()
        agents = (work / "b" / "AGENTS.md").read_text()
        assert "`toffee <env> plan`" in agents
        assert "`toffee <env> validate`" in agents
        assert "`toffee <env> check`" in agents
        assert "protected" in agents
        assert "modules/" in agents
        assert "vars/" in agents

    def test_no_credentials_are_written(self, work):
        for provider in ("aws", "google", "azurerm"):
            toffee("new", provider, "--provider", provider)
        text = "".join(
            (work / path).read_text()
            for path in files_under(work)
            if not path.endswith(".gitkeep")
        ).lower()
        for secret in ("access_key", "secret_key", "client_secret", "sas_token"):
            assert secret not in text


class TestSeparateState:
    @pytest.mark.parametrize("provider", ["aws", "google", "azurerm", "none"])
    def test_every_environment_gets_its_own_state(self, work, provider):
        toffee("new", "--provider", provider, "--envs", "dev,staging,prod")

        identities = set()
        for env in ("dev", "staging", "prod"):
            settings = read_settings(str(work / "vars" / f"{env}.tfbackend"))
            identities.add(json.dumps(settings, sort_keys=True))
        assert len(identities) == 3
        command = BaseCommand()
        assert command.check_state_isolation(["dev", "staging", "prod"], str(work))

    def test_state_commands_run_on_a_fresh_scaffold(self, work, mock_env):
        toffee("new", "--envs", "dev,staging")

        result = toffee("dev,staging", "plan", env=mock_env)

        assert result.exit_code == 0, result.output
        assert "would share" not in result.stderr

    def test_ready_environments_and_expected_diff(self, work):
        toffee("new", "--envs", "dev,prod")

        envs = toffee("info", "envs")
        diff = toffee("diff", "dev", "prod")

        assert envs.exit_code == 0
        for env in ("dev", "prod"):
            assert re.search(rf"{env}\s.*ready", envs.stdout)
        assert diff.exit_code == 0
        changed = [
            line for line in diff.stdout.splitlines() if not line.startswith(" ")
        ]
        assert changed == [
            "Variables differences",
            "environment",
            "Backend differences",
            "key",
        ]


class TestReruns:
    def test_rerun_has_nothing_to_create(self, work):
        toffee("new", "--envs", "dev,prod")
        before = {path: (work / path).read_bytes() for path in files_under(work)}

        result = toffee("new")

        assert result.exit_code == 0
        assert result.stdout == "Nothing to create; all files already exist in ./.\n"
        assert result.stderr == ""
        assert {
            path: (work / path).read_bytes() for path in files_under(work)
        } == before

    def test_adding_an_environment_reports_only_new_files(self, work):
        toffee("new")

        result = toffee("new", "--envs", "staging")

        assert result.exit_code == 0, result.output
        tree = result.stdout.split("\n\n")[1]
        assert tree == (
            "./\n└── vars/\n    ├── staging.tfvars\n    └── staging.tfbackend"
        )
        assert result.stdout.startswith("Created 2 files for project work:")
        assert "Skipped 9 files that already exist (not overwritten)." in result.stdout
        assert "main.tf" not in result.stdout
        assert next_steps(result.stdout) == [
            "Replace CHANGE-ME in vars/staging.tfbackend (bucket)",
            "toffee staging init",
            "toffee staging plan",
        ]

    def test_existing_files_are_never_overwritten(self, work):
        (work / "main.tf").write_text("# mine\n")
        (work / "vars").mkdir()
        (work / "vars" / "dev.tfvars").write_text('environment = "dev"\n')

        result = toffee("new")

        assert result.exit_code == 0
        assert (work / "main.tf").read_text() == "# mine\n"
        assert (work / "vars/dev.tfvars").read_text() == 'environment = "dev"\n'
        assert "Skipped 2 files that already exist" in result.stdout
        assert "main.tf" not in result.stdout

    def test_rerun_reuses_the_existing_provider_backend_and_project(self, work):
        toffee(
            "new", "--provider", "google", "--name", "shop", "--region", "europe-west1"
        )

        result = toffee("new", "--envs", "qa")

        assert result.exit_code == 0, result.output
        assert (work / "vars/qa.tfvars").read_text() == (
            'project     = "shop"\nproject_id  = "CHANGE-ME"\n'
            'environment = "qa"\nregion      = "europe-west1"\n'
        )
        assert read_settings(str(work / "vars/qa.tfbackend"))["prefix"] == "shop/qa"

    def test_existing_vars_dir_setting_is_respected(self, work):
        (work / ".toffee.json").write_text('{"vars_dir": "environments"}\n')

        result = toffee("new", "--provider", "none")

        assert result.exit_code == 0, result.output
        assert (work / "environments/dev.tfvars").is_file()
        assert not (work / "vars").exists()
        assert toffee("info", "envs").stdout.count("ready") == 1

    def test_dry_run_mirrors_output_and_writes_nothing(self, work):
        toffee("new", "--envs", "dev")
        before = files_under(work)

        dry = toffee("new", "--envs", "dev,prod", "--dry-run")

        assert dry.exit_code == 0
        assert files_under(work) == before
        assert dry.stdout == (
            "Would create 2 files for project work:\n\n"
            "./\n└── vars/\n    ├── prod.tfvars\n    └── prod.tfbackend\n\n"
            "Would skip 11 files that already exist (not overwritten).\n\n"
            "Dry run: nothing was written.\n"
        )

    def test_dry_run_in_an_empty_directory_writes_nothing(self, work):
        result = toffee("new", "svc", "--agents", "--dry-run")

        assert result.exit_code == 0
        assert os.listdir(work) == []
        assert result.stdout.startswith("Would create 12 files for project svc:")
        assert "AGENTS.md" in result.stdout


class TestGitignore:
    def test_appends_only_missing_lines(self, work):
        (work / ".gitignore").write_text("node_modules/\n.terraform/")

        result = toffee("new")

        text = (work / ".gitignore").read_text()
        assert text.startswith("node_modules/\n.terraform/\n\n# Added by toffee new\n")
        assert text.count(".terraform/") == 1
        assert "*.tfstate\n" in text
        assert "├── .gitignore (added 10 lines)" in result.stdout or (
            "└── .gitignore (added 10 lines)" in result.stdout
        )
        again = toffee("new")
        assert again.stdout.startswith("Nothing to create")
        assert (work / ".gitignore").read_text() == text

    def test_patterns_do_not_ignore_project_files(self, work):
        toffee("new")
        lines = [
            line
            for line in (work / ".gitignore").read_text().splitlines()
            if line and not line.startswith("#")
        ]
        assert ".terraform.lock.hcl" not in "\n".join(lines)
        assert "*.toffee.json" not in lines
        assert "?*.toffee.json" in lines

    @pytest.mark.skipif(shutil.which("git") is None, reason="git not installed")
    @pytest.mark.parametrize("existing", [None, "*.toffee.json\n"])
    def test_git_tracks_config_and_ignores_generated_files(self, work, existing):
        subprocess.run(["git", "init", "-q"], cwd=work, check=True)
        if existing:
            (work / ".gitignore").write_text(existing)
        toffee("new")

        def ignored(path):
            return (
                subprocess.run(
                    ["git", "check-ignore", "-q", "--no-index", path],
                    cwd=work,
                    env={**os.environ, "GIT_CONFIG_NOSYSTEM": "1"},
                    check=False,
                ).returncode
                == 0
            )

        for path in (
            ".toffee.json",
            ".terraform.lock.hcl",
            "vars/dev.tfvars",
            "vars/dev.tfbackend",
            "main.tf",
        ):
            assert not ignored(path), path
        for path in (
            ".terraform/providers/x",
            ".toffee/terraform-data/dev/x",
            "terraform.tfstate",
            "terraform.tfstate.backup",
            "state/dev/terraform.tfstate",
            "crash.log",
            "crash.123.log",
            "tfplan",
            "dev.tfplan",
            "tfplan.toffee.json",
            "dev.tfplan.toffee.json",
            "out.plan.toffee.json",
        ):
            assert ignored(path), path


class TestErrors:
    @pytest.mark.parametrize(
        "envs, expected",
        [
            (
                "new",
                "reserved for the Toffee command of the same name (reserved: "
                "config, diff, env, info, new)",
            ),
            (
                "dev.eu",
                "start with a letter or digit and contain only letters, "
                "digits, underscores, and hyphens",
            ),
            ("../prod", "start with a letter or digit"),
            ("dev,,prod", "for example --envs dev,prod"),
            ("Dev,dev", "differ only by case"),
        ],
    )
    def test_invalid_env_names_explain_the_rule(self, work, envs, expected):
        result = toffee("new", "svc", "--envs", envs)

        assert_one_line_error(result)
        assert expected in result.stderr
        assert os.listdir(work) == []

    @pytest.mark.parametrize(
        "option, value, expected",
        [
            (
                "--provider",
                "aws2",
                "Unknown --provider 'aws2'. Did you mean 'aws'? "
                "Choose from: aws, google, azurerm, none.",
            ),
            ("--provider", "gcp", "Did you mean 'google'?"),
            ("--provider", "azure", "Did you mean 'azurerm'?"),
            (
                "--backend",
                "s4",
                "Unknown --backend 's4'. Did you mean 's3'? "
                "Choose from: s3, gcs, azurerm, local.",
            ),
            ("--backend", "consul", "Choose from: s3, gcs, azurerm, local."),
            ("--region", 'us"east', "--region 'us\"east' may contain only"),
            ("--name", "my service", "--name 'my service' must start with a letter"),
            ("--template", "missing-dir", "Template directory not found: missing-dir"),
        ],
    )
    def test_invalid_options_are_actionable(self, work, option, value, expected):
        result = toffee("new", "svc", option, value)

        assert_one_line_error(result)
        assert expected in result.stderr
        assert os.listdir(work) == []

    def test_close_to_prod_warns_that_it_is_not_protected(self, work):
        result = toffee("new", "--envs", "dev,prdo")

        assert result.exit_code == 0
        assert result.stderr == (
            "Warning: 'prdo' is not protected like 'prod'. If it is production, "
            "name it 'prod' or add it to protected_environments in .toffee.json.\n"
        )
        assert toffee("new", "--envs", "dev,prod").stderr == ""

    def test_target_must_be_a_directory(self, work):
        (work / "file").write_text("")

        assert_one_line_error(toffee("new", "file"))

    def test_mismatched_backend_in_existing_project(self, work):
        toffee("new")

        result = toffee("new", "--backend", "gcs", "--envs", "qa")

        assert_one_line_error(result)
        assert "Omit --backend to use s3" in result.stderr
        assert not (work / "vars/qa.tfvars").exists()

    def test_invalid_existing_config_writes_nothing(self, work):
        (work / ".toffee.json").write_text("{not json")

        result = toffee("new")

        assert_one_line_error(result)
        assert "Cannot use the existing .toffee.json" in result.stderr
        assert os.listdir(work) == [".toffee.json"]

    @pytest.mark.skipif(
        hasattr(os, "geteuid") and os.geteuid() == 0, reason="root ignores permissions"
    )
    def test_unwritable_directory_is_a_clean_error(self, work):
        (work / "locked").mkdir()
        (work / "locked").chmod(stat.S_IRUSR | stat.S_IXUSR)
        try:
            result = toffee("new", "locked")
        finally:
            (work / "locked").chmod(stat.S_IRWXU)

        assert_one_line_error(result)
        assert "Cannot write the project" in result.stderr


class TestCustomTemplate:
    @pytest.fixture
    def template(self, tmp_path):
        root = tmp_path / "template"
        (root / "vars").mkdir(parents=True)
        (root / "envs" / "__env__").mkdir(parents=True)
        (root / "main.tf").write_text(
            "locals {\n"
            '  name   = "${var.project}-{{project}}"\n'
            '  banner = "%{ if true }{{ region }}%{ endif }"\n'
            '  helm   = "{{ .Values.image }}"\n'
            '  dollar = "$${literal}"\n'
            "}\n"
        )
        (root / "vars" / "__env__.tfvars").write_text('environment = "{{env}}"\n')
        (root / "vars" / "__env__.tfbackend").write_text(
            'path = "state/{{env}}/terraform.tfstate"\n'
        )
        (root / "envs" / "__env__" / "README.md").write_text(
            "{{env}} of {{project}} on {{provider}}/{{backend}}\n"
        )
        (root / "blob.bin").write_bytes(b"\xff\x00{{project}}")
        (root / ".git").mkdir()
        (root / ".git" / "HEAD").write_text("ref: refs/heads/main\n")
        return root

    def test_tokens_and_env_paths_are_rendered(self, work, template):
        result = toffee(
            "new",
            "out",
            "--template",
            str(template),
            "--envs",
            "dev,prod",
            "--name",
            "demo",
            "--backend",
            "local",
        )

        assert result.exit_code == 0, result.output
        out = work / "out"
        assert files_under(out) == [
            "blob.bin",
            "envs/dev/README.md",
            "envs/prod/README.md",
            "main.tf",
            "vars/dev.tfbackend",
            "vars/dev.tfvars",
            "vars/prod.tfbackend",
            "vars/prod.tfvars",
        ]
        main = (out / "main.tf").read_text()
        assert '"${var.project}-demo"' in main
        assert '"%{ if true }us-east-1%{ endif }"' in main
        assert '"{{ .Values.image }}"' in main
        assert '"$${literal}"' in main
        assert (out / "vars/prod.tfvars").read_text() == 'environment = "prod"\n'
        assert (out / "envs/dev/README.md").read_text() == "dev of demo on aws/local\n"
        assert (out / "blob.bin").read_bytes() == b"\xff\x00{{project}}"
        assert next_steps(result.stdout) == [
            "cd out && toffee dev init",
            "toffee dev plan",
        ]

    def test_env_token_outside_env_paths_is_an_error(self, work, template):
        (template / "notes.md").write_text("{{env}}\n")

        result = toffee("new", "out", "--template", str(template))

        assert_one_line_error(result)
        assert "notes.md uses {{env}}" in result.stderr
        assert not (work / "out").exists()

    @pytest.mark.parametrize("kind", ["file", "directory"])
    def test_symlinks_in_the_template_are_refused(self, work, template, tmp_path, kind):
        outside = tmp_path / "outside"
        outside.mkdir()
        (outside / "secret.tf").write_text("secret\n")
        if kind == "file":
            (template / "link.tf").symlink_to(outside / "secret.tf")
        else:
            (template / "linked").symlink_to(outside, target_is_directory=True)

        result = toffee("new", "out", "--template", str(template))

        assert_one_line_error(result)
        assert "symlink" in result.stderr
        assert not (work / "out").exists()

    def test_names_from_templates_cannot_inject_markup(self, work, template):
        (template / "[bold red]x[red].tf").write_text("")

        result = toffee("new", "out", "--template", str(template))

        assert result.exit_code == 0
        assert "── [bold red]x[red].tf" in result.stdout


class TestSymlinkedTargets:
    def test_refuses_to_write_through_a_symlinked_directory(self, work, tmp_path):
        outside = tmp_path / "outside"
        outside.mkdir()
        (work / "vars").symlink_to(outside, target_is_directory=True)

        result = toffee("new")

        assert_one_line_error(result)
        assert "Refusing to write through symlink: vars/dev.tfvars" in result.stderr
        assert os.listdir(outside) == []
        assert sorted(os.listdir(work)) == ["vars"]

    def test_refuses_to_append_through_a_symlinked_gitignore(self, work, tmp_path):
        outside = tmp_path / "outside.gitignore"
        outside.write_text("x\n")
        (work / ".gitignore").symlink_to(outside)

        result = toffee("new")

        assert_one_line_error(result)
        assert outside.read_text() == "x\n"

    def test_existing_symlinked_files_are_skipped_not_followed(self, work, tmp_path):
        outside = tmp_path / "main.tf"
        outside.write_text("# shared\n")
        (work / "main.tf").symlink_to(outside)

        result = toffee("new")

        assert result.exit_code == 0
        assert outside.read_text() == "# shared\n"


class TestPlaceholderSafeguard:
    def test_init_stops_until_the_placeholder_is_replaced(
        self, work, mock_env, mock_terraform_log
    ):
        toffee("new", "--envs", "dev,prod")

        blocked = toffee("dev,prod", "init", env=mock_env)

        assert blocked.exit_code == 1
        assert blocked.stderr.splitlines() == [
            "Error: Replace CHANGE-ME in vars/dev.tfbackend (bucket) before "
            "running: toffee dev init",
            "Error: Replace CHANGE-ME in vars/prod.tfbackend (bucket) before "
            "running: toffee prod init",
        ]
        assert mock_terraform_log.read_text() == ""

        for env in ("dev", "prod"):
            path = work / "vars" / f"{env}.tfbackend"
            path.write_text(path.read_text().replace(PLACEHOLDER, "acme-state"))
        allowed = toffee("dev,prod", "init", env=mock_env)

        assert allowed.exit_code == 0, allowed.output
        assert mock_terraform_log.read_text().count(" init ") == 2

    def test_inline_backend_config_supplies_the_value(
        self, work, mock_env, mock_terraform_log
    ):
        toffee("new")

        result = toffee("dev", "init", "-backend-config=bucket=acme", env=mock_env)

        assert result.exit_code == 0, result.output
        assert "init" in mock_terraform_log.read_text()

    def test_other_commands_are_not_blocked(self, work, mock_env):
        toffee("new")

        assert toffee("dev", "validate", env=mock_env).exit_code == 0


class TestUserExperience:
    def test_golden_default_output(self, work):
        result = toffee("new", "my-service")

        assert result.exit_code == 0
        assert result.stderr == ""
        assert result.stdout == GOLDEN_DEFAULT_OUTPUT

    def test_readme_shows_the_real_default_output(self):
        readme = (Path(__file__).parent.parent / "README.md").read_text()

        assert f"```text\n{GOLDEN_DEFAULT_OUTPUT}```" in readme

    def test_output_is_plain_text(self, work):
        result = toffee("new", "svc", "--envs", "dev,prod", "--agents")

        assert "\x1b" not in result.output
        assert "[/" not in result.output and "[bold" not in result.output
        assert len(next_steps(result.stdout)) <= 3

    def test_long_paths_are_not_wrapped(self, work):
        name = "a-very-long-project-directory-name-" * 3

        result = toffee("new", name)

        assert f"  1. Replace CHANGE-ME in {name}/vars/dev.tfbackend (bucket)" in (
            result.stdout.splitlines()
        )
        assert f"  2. cd {name} && toffee dev init" in result.stdout.splitlines()

    @pytest.mark.parametrize("directory", [None, "svc", "nested/dir"])
    def test_printed_next_steps_work(self, work, mock_env, directory):
        args = ["new", "--provider", "none", "--envs", "dev,staging"]
        result = toffee(*args, *([directory] if directory else []))

        steps = next_steps(result.stdout)
        assert steps[-1] == "toffee dev plan"
        for step in steps:
            ran = run_step(step, mock_env)
            assert ran.exit_code == 0, (step, ran.output)

    def test_printed_edit_step_names_the_exact_file_and_key(self, work, mock_env):
        result = toffee("new", "svc")
        edit, *commands = next_steps(result.stdout)

        match = re.fullmatch(r"Replace CHANGE-ME in (\S+) \((\w+)\)", edit)
        path, key = match.groups()
        text = (work / path).read_text()
        assert re.search(rf'^{key}\s+= "{PLACEHOLDER}"$', text, re.MULTILINE)
        (work / path).write_text(text.replace(PLACEHOLDER, "acme-state"))
        for step in commands:
            ran = run_step(step, mock_env)
            assert ran.exit_code == 0, (step, ran.output)

    def test_help_has_purpose_examples_and_defaults(self):
        result = toffee("new", "--help")

        lines = result.stdout.splitlines()
        assert lines[2].strip() == "Create a Terraform project set up for Toffee."
        assert lines[4].strip() == "Examples:"
        examples = [line.strip() for line in lines[5:9] if line.strip()]
        assert 2 <= len(examples) <= 3
        assert all(example.startswith("toffee new") for example in examples)
        for default in ("[default: dev]", "[default: aws]"):
            assert default in result.stdout
        assert "(matches --provider)" in result.stdout
        assert "(directory name)" in result.stdout

    def test_top_level_help_lists_new(self):
        result = toffee("--help")

        assert re.search(
            r"^  new\s+Create a Terraform project set up for Toffee\.$",
            result.stdout,
            re.MULTILINE,
        )
