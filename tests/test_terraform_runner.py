"""Tests for Terraform command building."""

import pytest

from toffee.core.environment import Environment
from toffee.core.terraform import TerraformRunner, display_command, uses_state

VARS = "-var-file=vars/dev.tfvars"
BACKEND = "-backend-config=vars/dev.tfbackend"


class TestTerraformRunner:
    @pytest.fixture(autouse=True)
    def _project(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        self.project = tmp_path
        self.runner = TerraformRunner(terraform_path="/usr/bin/terraform")

    def _make_env(self, tmp_path=None):
        vars_dir = self.project / "vars"
        vars_dir.mkdir(exist_ok=True)
        vars_file = vars_dir / "dev.tfvars"
        backend_file = vars_dir / "dev.tfbackend"
        vars_file.write_text('environment = "dev"\n')
        backend_file.write_text('path = "dev.tfstate"\n')
        return Environment(
            name="dev",
            vars_file=str(vars_file),
            backend_file=str(backend_file),
        )

    def test_build_init_command(self):
        env = self._make_env()
        cmd = self.runner.build_command("init", env)
        assert cmd == ["/usr/bin/terraform", "init", BACKEND, "-reconfigure"]

    def test_build_plan_command(self):
        env = self._make_env()
        cmd = self.runner.build_command("plan", env, ["-out=plan.out"])
        assert cmd == ["/usr/bin/terraform", "plan", VARS, "-out=plan.out"]

    def test_build_validate_without_env(self):
        cmd = self.runner.build_command("validate")
        assert cmd == ["/usr/bin/terraform", "validate"]

    def test_build_unknown_command_is_untouched(self):
        env = self._make_env()
        cmd = self.runner.build_command("customcmd", env, ["-flag"])
        assert cmd == ["/usr/bin/terraform", "customcmd", "-flag"]

    def test_apply_saved_plan_does_not_add_var_file(self):
        env = self._make_env()
        plan_file = self.project / "release-plan"
        plan_file.write_bytes(b"PK\x03\x04plan")
        cmd = self.runner.build_command("apply", env, [str(plan_file)])
        assert cmd == ["/usr/bin/terraform", "apply", str(plan_file)]

    def test_existing_files_in_flag_values_are_not_saved_plans(self):
        env = self._make_env()
        (self.project / "extra.tfvars").write_bytes(b"PK\x03\x04not a plan")
        (self.project / "aws_instance.web").write_bytes(b"PK\x03\x04not a plan")
        args = ["-var-file", "extra.tfvars", "-target", "aws_instance.web"]

        cmd = self.runner.build_command("apply", env, args)

        assert cmd == ["/usr/bin/terraform", "apply", VARS, *args]

    def test_non_plan_positional_keeps_var_file(self):
        env = self._make_env()
        (self.project / "notes.txt").write_text("not a plan")

        cmd = self.runner.build_command("apply", env, ["notes.txt"])

        assert VARS in cmd

    def test_saved_plan_is_resolved_against_chdir(self):
        env = self._make_env()
        (self.project / "sub").mkdir()
        (self.project / "sub" / "tfplan").write_bytes(b"PK\x03\x04plan")

        cmd = self.runner.build_command(
            "apply", env, ["tfplan"], global_args=["-chdir=sub"]
        )

        assert cmd == ["/usr/bin/terraform", "-chdir=sub", "apply", "tfplan"]

    def test_env_files_are_relative_to_chdir(self):
        env = self._make_env()
        (self.project / "sub").mkdir()

        cmd = self.runner.build_command("plan", env, global_args=["-chdir=sub"])

        assert cmd == [
            "/usr/bin/terraform",
            "-chdir=sub",
            "plan",
            "-var-file=../vars/dev.tfvars",
        ]

    def test_env_files_are_relative_through_symlinked_directory(
        self, tmp_path, monkeypatch
    ):
        env = self._make_env()
        link = tmp_path.parent / f"{tmp_path.name}-link"
        link.symlink_to(tmp_path, target_is_directory=True)
        monkeypatch.chdir(link)

        cmd = self.runner.build_command("init", env)

        assert cmd[2] == BACKEND

    def test_init_migrate_state_does_not_add_reconfigure(self):
        env = self._make_env()
        cmd = self.runner.build_command("init", env, ["-migrate-state"])
        assert cmd == ["/usr/bin/terraform", "init", BACKEND, "-migrate-state"]

    def test_supplemental_backend_config_keeps_env_file(self):
        env = self._make_env()
        cmd = self.runner.build_command(
            "init", env, ["-backend-config=workspace_dir=ws"]
        )
        assert cmd == [
            "/usr/bin/terraform",
            "init",
            BACKEND,
            "-reconfigure",
            "-backend-config=workspace_dir=ws",
        ]

    def test_reconfigure_variant_is_not_duplicated(self):
        env = self._make_env()
        cmd = self.runner.build_command("init", env, ["--reconfigure"])
        assert cmd == ["/usr/bin/terraform", "init", BACKEND, "--reconfigure"]

    def test_global_args_are_before_command(self):
        env = self._make_env()
        cmd = self.runner.build_command("plan", env, global_args=["-compact-warnings"])
        assert cmd == ["/usr/bin/terraform", "-compact-warnings", "plan", VARS]

    def test_non_interactive_adds_input_false(self):
        env = self._make_env()
        cmd = self.runner.build_command(
            "apply", env, ["-auto-approve"], non_interactive=True
        )
        assert cmd == [
            "/usr/bin/terraform",
            "apply",
            VARS,
            "-input=false",
            "-auto-approve",
        ]

    def test_non_interactive_respects_user_input_flag(self):
        env = self._make_env()
        cmd = self.runner.build_command(
            "plan", env, ["-input=true"], non_interactive=True
        )
        assert "-input=false" not in cmd

    def test_non_interactive_skips_commands_without_input_flag(self):
        env = self._make_env()
        cmd = self.runner.build_command("output", env, non_interactive=True)
        assert cmd == ["/usr/bin/terraform", "output"]

    def test_skips_missing_files(self):
        env = Environment(
            name="dev",
            vars_file=str(self.project / "missing.tfvars"),
            backend_file=str(self.project / "missing.tfbackend"),
        )
        cmd = self.runner.build_command("plan", env)
        assert cmd == ["/usr/bin/terraform", "plan"]
        assert not any(arg.startswith("-var-file=") for arg in cmd)


def test_display_command_redacts_values():
    shown = display_command(
        [
            "terraform",
            "init",
            "-backend-config=vars/dev.tfbackend",
            "-backend-config=secret_key=hunter2",
            "-backend-config",
            "access_key=AKIA",
            "-var",
            "db_password=pw",
            "-var=cidrs=[/]",
            "-var-file=vars/dev.tfvars",
        ]
    )

    assert "hunter2" not in shown
    assert "AKIA" not in shown
    assert "pw" not in shown.replace("password", "")
    assert "-backend-config=vars/dev.tfbackend" in shown
    assert "-backend-config=secret_key=<redacted>" in shown
    assert "'db_password=<redacted>'" in shown
    assert "-var-file=vars/dev.tfvars" in shown


def test_display_command_replaces_control_characters():
    assert "\x1b" not in display_command(["terraform", "plan", "-target=\x1b[2J"])


@pytest.mark.parametrize(
    "command, args, global_args",
    [
        ("fmt", ["-recursive"], []),
        ("validate", [], []),
        ("version", ["-json"], []),
        ("-version", [], []),
        ("get", [], []),
        ("modules", [], []),
        ("metadata", ["functions", "-json"], []),
        ("providers", ["lock", "-platform=linux_amd64"], []),
        ("providers", ["mirror", "dir"], []),
        ("login", [], []),
        ("logout", ["example.com"], []),
        ("plan", ["-help"], []),
        ("apply", ["-auto-approve", "-h"], []),
        ("state", ["rm", "a", "--help"], []),
        ("plan", [], ["-help"]),
        ("-help", [], []),
    ],
)
def test_commands_that_never_touch_state(command, args, global_args):
    assert not uses_state(command, args, global_args)


@pytest.mark.parametrize(
    "command, args",
    [
        ("init", []),
        ("plan", []),
        ("apply", []),
        ("console", []),
        ("graph", []),
        ("output", []),
        ("show", []),
        ("query", []),
        ("providers", []),
        ("providers", ["schema", "-json"]),
        ("providers", ["-help=false"]),
        ("state", ["list"]),
        ("workspace", ["show"]),
        ("some-future-command", []),
        ("apply", ["--", "-help"]),
        ("plan", ["-var", "help=-h-"]),
    ],
)
def test_state_commands_and_unknown_commands_use_state(command, args):
    assert uses_state(command, args)
