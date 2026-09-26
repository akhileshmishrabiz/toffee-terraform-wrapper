"""Tests for Terraform command building."""

from toffee.core.environment import Environment
from toffee.core.terraform import TerraformRunner


class TestTerraformRunner:
    def setup_method(self):
        self.runner = TerraformRunner(terraform_path="/usr/bin/terraform")

    def _make_env(self, tmp_path):
        vars_dir = tmp_path / "vars"
        vars_dir.mkdir()
        vars_file = vars_dir / "dev.tfvars"
        backend_file = vars_dir / "dev.tfbackend"
        vars_file.write_text('environment = "dev"\n')
        backend_file.write_text('path = "dev.tfstate"\n')
        return Environment(
            name="dev",
            vars_file=str(vars_file),
            backend_file=str(backend_file),
        )

    def test_build_init_command(self, tmp_path):
        env = self._make_env(tmp_path)
        cmd = self.runner.build_command("init", env)
        assert cmd == [
            "/usr/bin/terraform",
            "init",
            f"-backend-config={env.backend_file}",
            "-reconfigure",
        ]

    def test_build_plan_command(self, tmp_path):
        env = self._make_env(tmp_path)
        cmd = self.runner.build_command("plan", env, ["-out=plan.out"])
        assert cmd == [
            "/usr/bin/terraform",
            "plan",
            f"-var-file={env.vars_file}",
            "-out=plan.out",
        ]

    def test_build_validate_without_env(self):
        cmd = self.runner.build_command("validate")
        assert cmd == ["/usr/bin/terraform", "validate"]

    def test_build_unknown_command_is_untouched(self, tmp_path):
        env = self._make_env(tmp_path)
        cmd = self.runner.build_command("customcmd", env, ["-flag"])
        assert cmd == [
            "/usr/bin/terraform",
            "customcmd",
            "-flag",
        ]

    def test_apply_saved_plan_does_not_add_var_file(self, tmp_path):
        env = self._make_env(tmp_path)
        plan_file = tmp_path / "release-plan"
        plan_file.touch()
        cmd = self.runner.build_command("apply", env, [str(plan_file)])
        assert cmd == ["/usr/bin/terraform", "apply", str(plan_file)]

    def test_init_migrate_state_does_not_add_reconfigure(self, tmp_path):
        env = self._make_env(tmp_path)
        cmd = self.runner.build_command("init", env, ["-migrate-state"])
        assert cmd == [
            "/usr/bin/terraform",
            "init",
            f"-backend-config={env.backend_file}",
            "-migrate-state",
        ]

    def test_user_backend_override_is_not_duplicated(self, tmp_path):
        env = self._make_env(tmp_path)
        cmd = self.runner.build_command(
            "init", env, ["-backend-config=custom.tfbackend"]
        )
        assert cmd == [
            "/usr/bin/terraform",
            "init",
            "-backend-config=custom.tfbackend",
        ]

    def test_global_args_are_before_command(self, tmp_path):
        env = self._make_env(tmp_path)
        cmd = self.runner.build_command(
            "plan", env, global_args=["-compact-warnings"]
        )
        assert cmd == [
            "/usr/bin/terraform",
            "-compact-warnings",
            "plan",
            f"-var-file={env.vars_file}",
        ]

    def test_skips_missing_files(self, tmp_path):
        env = Environment(
            name="dev",
            vars_file=str(tmp_path / "missing.tfvars"),
            backend_file=str(tmp_path / "missing.tfbackend"),
        )
        cmd = self.runner.build_command("plan", env)
        assert cmd == ["/usr/bin/terraform", "plan"]
        assert not any(arg.startswith("-var-file=") for arg in cmd)
