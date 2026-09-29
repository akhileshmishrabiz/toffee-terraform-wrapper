"""Integration tests against real Terraform when available.

Toffee is run from this checkout with ``python -m toffee`` so the tests never
exercise an unrelated ``toffee`` installed on PATH.
"""

import json
import os
import shutil
import subprocess
import sys

import pytest

pytestmark = pytest.mark.skipif(
    shutil.which("terraform") is None, reason="terraform binary not installed"
)


def _toffee(project, *args, input=None):
    return subprocess.run(
        [sys.executable, "-m", "toffee", *args],
        cwd=project,
        input=input,
        text=True,
        capture_output=True,
        check=False,
    )


@pytest.fixture
def project(real_terraform_project, tmp_path):
    state_root = tmp_path / "state"
    state_root.mkdir()
    for env in ("dev", "staging", "prod"):
        backend = real_terraform_project / "vars" / f"{env}.tfbackend"
        backend.write_text(f'path = "{state_root}/{env}/terraform.tfstate"\n')

    config = {"vars_dir": "vars", "terraform_path": "terraform", "auto_approve": True}
    (real_terraform_project / ".toffee.json").write_text(json.dumps(config, indent=2))
    return real_terraform_project, state_root


def _assert_ok(result):
    assert result.returncode == 0, result.stdout + result.stderr


class TestRealTerraform:
    def test_init_validate_plan_apply_destroy(self, project):
        project, state_root = project

        for env in ("dev", "staging"):
            _assert_ok(_toffee(project, env, "init"))

        for env in ("dev", "staging"):
            _assert_ok(_toffee(project, env, "validate"))
            _assert_ok(_toffee(project, env, "plan"))
            _assert_ok(_toffee(project, env, "apply"))
            output = _toffee(project, env, "output")
            _assert_ok(output)
            assert env in output.stdout

        for env in ("dev", "staging"):
            assert (state_root / env / "terraform.tfstate").is_file()

        outputs = _toffee(project, "dev,staging", "output", "-json", "--parallel")
        _assert_ok(outputs)
        decoder = json.JSONDecoder()
        first, end = decoder.raw_decode(outputs.stdout)
        second, _ = decoder.raw_decode(outputs.stdout[end:].lstrip())
        assert first["environment"]["value"] == "dev"
        assert second["environment"]["value"] == "staging"

        _assert_ok(_toffee(project, "dev,staging", "destroy", input="y\n"))

    def test_protected_bypasses_are_blocked(self, project):
        project, state_root = project
        for env in ("dev", "prod"):
            _assert_ok(_toffee(project, env, "init"))

        empty = _toffee(project, "prod", "", "apply", "-auto-approve")
        assert empty.returncode == 2
        assert "Empty or whitespace-only arguments" in empty.stderr

        _assert_ok(_toffee(project, "prod", "plan", "-out=tfplan"))
        crossed = _toffee(project, "dev", "apply", "tfplan", input="y\n")
        assert crossed.returncode == 1
        assert "created for environment 'prod', not 'dev'" in crossed.stderr

        declined = _toffee(project, "prod", "apply", "tfplan", input="")
        assert declined.returncode == 1
        assert "Continue? [y/N]" in declined.stderr
        assert not (state_root / "prod" / "terraform.tfstate").exists()

        _assert_ok(_toffee(project, "prod", "apply", "tfplan", input="y\n"))
        assert (state_root / "prod" / "terraform.tfstate").is_file()
        assert not (state_root / "dev" / "terraform.tfstate").exists()

    def test_init_works_through_a_symlinked_project_path(self, project, tmp_path):
        project, _state_root = project
        # Like macOS /tmp -> /private/tmp: the logical and physical parents differ.
        link = tmp_path / "a" / "b" / "linked-project"
        link.parent.mkdir(parents=True)
        link.symlink_to(project, target_is_directory=True)
        env = {**os.environ, "PWD": str(link)}

        result = subprocess.run(
            [sys.executable, "-m", "toffee", "dev", "init"],
            cwd=link,
            env=env,
            text=True,
            capture_output=True,
            check=False,
        )

        _assert_ok(result)
