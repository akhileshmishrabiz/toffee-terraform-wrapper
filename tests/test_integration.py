"""Integration tests against real Terraform when available."""

import json
import os
import shutil
import subprocess

import pytest


@pytest.mark.skipif(
    shutil.which("terraform") is None, reason="terraform binary not installed"
)
class TestRealTerraform:
    def test_init_validate_plan_apply_destroy(self, real_terraform_project, tmp_path):
        project = real_terraform_project
        state_root = tmp_path / "state"
        state_root.mkdir()

        for env in ("dev", "staging"):
            backend = project / "vars" / f"{env}.tfbackend"
            backend.write_text(f'path = "{state_root}/{env}/terraform.tfstate"\n')

        config = {
            "vars_dir": "vars",
            "terraform_path": "terraform",
            "auto_approve": True,
        }
        (project / ".toffee.json").write_text(json.dumps(config, indent=2))

        previous = os.getcwd()
        os.chdir(project)
        try:
            for env in ("dev", "staging"):
                assert (
                    subprocess.run(
                        ["toffee", env, "init"], check=False
                    ).returncode
                    == 0
                )

            for env in ("dev", "staging"):
                assert (
                    subprocess.run(
                        ["toffee", env, "validate"], check=False
                    ).returncode
                    == 0
                )
                assert (
                    subprocess.run(
                        ["toffee", env, "plan"], check=False
                    ).returncode
                    == 0
                )
                assert (
                    subprocess.run(
                        ["toffee", env, "apply"], check=False
                    ).returncode
                    == 0
                )
                output = subprocess.run(
                    ["toffee", env, "output"],
                    check=False,
                    capture_output=True,
                    text=True,
                )
                assert output.returncode == 0
                assert env in output.stdout

            for env in ("dev", "staging"):
                assert (state_root / env / "terraform.tfstate").is_file()

            assert (
                subprocess.run(
                    ["toffee", "dev,staging", "destroy"],
                    input="y\n",
                    text=True,
                    check=False,
                ).returncode
                == 0
            )
        finally:
            os.chdir(previous)
