"""Configuration loading, validation, trust, and persistence."""

import json
import os
import stat

import pytest

from toffee.core.config import Config, ConfigError
from toffee.core.environment import EnvironmentManager


def _write_global(home, content):
    config_dir = home / ".toffee"
    config_dir.mkdir(exist_ok=True)
    config_file = config_dir / "config.json"
    config_file.write_text(content)
    return config_file


def _write_project(project, content):
    (project / ".toffee.json").write_text(content)


class TestLoading:
    def test_config_does_not_create_home_directory(self, isolated_home):
        Config()

        assert not (isolated_home / ".toffee").exists()

    def test_read_only_home_does_not_crash(self, invoke, isolated_home):
        isolated_home.chmod(stat.S_IRUSR | stat.S_IXUSR)
        try:
            result = invoke("info", "envs")
        finally:
            isolated_home.chmod(stat.S_IRWXU)

        assert result.exit_code == 0
        assert "dev" in result.stdout

    @pytest.mark.parametrize(
        "content, message",
        [
            ("[]", "must contain a JSON object"),
            ("{not json", "is not valid JSON"),
            ('{"vars_dir": null}', "vars_dir must be a non-empty string"),
            ('{"auto_approve": "false"}', "auto_approve must be true or false"),
            ('{"protected_environments": [1]}', "protected_environments must be a list"),
        ],
    )
    def test_invalid_global_config_is_a_clean_error(
        self, invoke, isolated_home, mock_terraform_log, content, message
    ):
        _write_global(isolated_home, content)

        result = invoke("dev", "plan")

        assert result.exit_code == 1
        assert message in result.stderr
        assert "Traceback" not in result.output
        assert mock_terraform_log.read_text() == ""

    @pytest.mark.parametrize(
        "content, message",
        [
            ("null", "must contain a JSON object"),
            ('{"vars_dir": null}', "vars_dir must be a non-empty string"),
            ('{"auto_approve": "false"}', "auto_approve must be true or false"),
        ],
    )
    def test_invalid_project_config_is_a_clean_error(
        self, invoke, project_dir, mock_terraform_log, content, message
    ):
        project, _, _ = project_dir
        _write_project(project, content)

        result = invoke("dev", "apply")

        assert result.exit_code == 1
        assert message in result.stderr
        assert mock_terraform_log.read_text() == ""

    def test_unknown_keys_are_ignored(self, invoke, project_dir):
        project, _, _ = project_dir
        _write_project(project, '{"future_setting": {"a": 1}}')

        assert invoke("dev", "plan").exit_code == 0


class TestTerraformPathTrust:
    def test_project_cannot_choose_an_explicit_binary(
        self, invoke, project_dir, tmp_path
    ):
        project, _, _ = project_dir
        marker = tmp_path / "ran"
        evil = tmp_path / "evil"
        evil.write_text(f"#!/bin/sh\ntouch {marker}\n")
        evil.chmod(0o755)
        _write_project(project, json.dumps({"terraform_path": str(evil)}))

        result = invoke("info", "version")

        assert result.exit_code == 1
        assert "can only name an executable on PATH" in result.stderr
        assert not marker.exists()

    @pytest.mark.parametrize("value", ["./terraform", "bin/terraform", ".."])
    def test_relative_paths_are_explicit_paths(self, value):
        from toffee.core.config import is_bare_executable_name

        assert not is_bare_executable_name(value)

    def test_project_may_name_an_executable(self, invoke, project_dir):
        project, _, env = project_dir
        _write_project(project, '{"terraform_path": "tofu"}')

        result = invoke("config", "show", extra_env={"TOFFEE_TERRAFORM_PATH": ""})

        assert result.exit_code == 0
        assert "tofu" in result.stdout
        assert "Project" in result.stdout

    def test_global_config_may_use_an_explicit_path(
        self, invoke, project_dir, isolated_home, mock_terraform_log
    ):
        project, _, env = project_dir
        _write_project(project, "{}")
        _write_global(
            isolated_home, json.dumps({"terraform_path": env["TOFFEE_TERRAFORM_PATH"]})
        )

        result = invoke("dev", "plan", extra_env={"TOFFEE_TERRAFORM_PATH": ""})

        assert result.exit_code == 0
        assert " plan " in mock_terraform_log.read_text()

    def test_environment_variable_takes_precedence(self, invoke):
        result = invoke("config", "show")

        assert result.exit_code == 0
        assert "Environment" in result.stdout

    def test_config_set_project_refuses_explicit_path(self, invoke, project_dir):
        project, _, _ = project_dir
        before = (project / ".toffee.json").read_text()

        result = invoke("config", "set", "terraform_path", "/opt/tf", "--project")

        assert result.exit_code == 1
        assert "can only name an executable on PATH" in result.stderr
        assert (project / ".toffee.json").read_text() == before

    def test_config_set_global_accepts_explicit_path(self, invoke, isolated_home):
        result = invoke("config", "set", "terraform_path", "/opt/tf/terraform")

        assert result.exit_code == 0
        saved = json.loads((isolated_home / ".toffee" / "config.json").read_text())
        assert saved == {"terraform_path": "/opt/tf/terraform"}


class TestSaving:
    def test_global_save_creates_directory_lazily(self, invoke, isolated_home):
        result = invoke("config", "set", "verbose", "true")

        assert result.exit_code == 0
        assert json.loads((isolated_home / ".toffee" / "config.json").read_text()) == {
            "verbose": True
        }

    def test_global_save_failure_returns_error(self, invoke, isolated_home):
        isolated_home.chmod(stat.S_IRUSR | stat.S_IXUSR)
        try:
            result = invoke("config", "set", "verbose", "true")
        finally:
            isolated_home.chmod(stat.S_IRWXU)

        assert result.exit_code == 1
        assert "cannot write" in result.stderr
        assert "Set global" not in result.output

    def test_corrupt_global_config_is_not_overwritten(self, invoke, isolated_home):
        config_file = _write_global(isolated_home, '{"verbose": true,')

        result = invoke("config", "set", "auto_approve", "false")

        assert result.exit_code == 1
        assert config_file.read_text() == '{"verbose": true,'

    def test_corrupt_project_config_is_not_overwritten(self, invoke, project_dir):
        project, _, _ = project_dir
        _write_project(project, '{"vars_dir": "vars",')

        result = invoke("config", "set", "auto_approve", "true", "--project")

        assert result.exit_code == 1
        assert (project / ".toffee.json").read_text() == '{"vars_dir": "vars",'

    def test_project_set_preserves_other_keys(self, invoke, project_dir):
        project, _, _ = project_dir
        _write_project(project, '{"vars_dir": "vars", "future_setting": 1}')

        assert invoke("config", "set", "auto_approve", "true", "--project").exit_code == 0

        assert json.loads((project / ".toffee.json").read_text()) == {
            "vars_dir": "vars",
            "future_setting": 1,
            "auto_approve": True,
        }

    @pytest.mark.skipif(os.geteuid() == 0, reason="root ignores file permissions")
    def test_unwritable_project_config_is_a_clean_error(self, invoke, project_dir):
        project, _, _ = project_dir
        project.chmod(stat.S_IRUSR | stat.S_IXUSR)
        (project / ".toffee.json").chmod(stat.S_IRUSR)
        try:
            result = invoke("config", "set", "auto_approve", "true", "--project")
        finally:
            project.chmod(stat.S_IRWXU)
            (project / ".toffee.json").chmod(stat.S_IRUSR | stat.S_IWUSR)

        assert result.exit_code == 1
        assert "cannot write" in result.stderr

    def test_config_set_value_is_not_markup(self, invoke, project_dir):
        result = invoke("config", "set", "vars_dir", "[/]vars", "--project")

        assert result.exit_code == 0
        assert "[/]vars" in result.stdout

    def test_set_invalid_value_raises(self, isolated_home):
        with pytest.raises(ConfigError):
            Config().set("verbose", "yes")


class TestEnvironmentNames:
    def test_trailing_newline_is_rejected(self, invoke, project_dir):
        project, _, _ = project_dir

        result = invoke("env", "create", "qa\n")

        assert result.exit_code == 1
        assert not any(name.startswith("qa") for name in os.listdir(project / "vars"))

    def test_discovery_lists_only_valid_names(self, tmp_path):
        vars_dir = tmp_path / "vars"
        vars_dir.mkdir()
        for name in ("dev", "config", "dev.eu", "my env", "[blink]staging", "a\x1bb"):
            (vars_dir / f"{name}.tfvars").write_text("")

        manager = EnvironmentManager(vars_dir=str(vars_dir))

        assert manager.get_environment_names() == ["dev"]

    def test_info_envs_renders_names_as_plain_text(self, invoke, project_dir):
        project, _, _ = project_dir
        (project / "vars" / "[blink]x.tfvars").write_text("")

        result = invoke("info", "envs")

        assert result.exit_code == 0
        assert "[blink]" not in result.stdout
        assert "dev" in result.stdout
