"""CLI integration tests using a mock terraform binary."""

import json


class TestCLI:
    def test_version(self, invoke):
        result = invoke("--version")
        assert result.exit_code == 0
        assert "Toffee version" in result.stdout

    def test_info_envs(self, invoke):
        result = invoke("info", "envs")
        assert result.exit_code == 0
        assert "dev" in result.stdout
        assert "staging" in result.stdout

    def test_plan_single_env(self, invoke, mock_terraform_log):
        result = invoke("plan", "dev")
        assert result.exit_code == 0
        log = mock_terraform_log.read_text()
        assert "plan" in log
        assert "-var-file=" in log
        assert "dev.tfvars" in log

    def test_plan_multiple_envs(self, invoke, mock_terraform_log):
        result = invoke("plan", "dev", "staging")
        assert result.exit_code == 0
        log = mock_terraform_log.read_text()
        assert log.count("plan") == 2
        assert "dev.tfvars" in log
        assert "staging.tfvars" in log

    def test_plan_all_envs(self, invoke, mock_terraform_log):
        result = invoke("plan", "--all")
        assert result.exit_code == 0
        log = mock_terraform_log.read_text()
        assert log.count("plan") == 2

    def test_init_includes_backend_config(self, invoke, mock_terraform_log):
        result = invoke("init", "dev")
        assert result.exit_code == 0
        log = mock_terraform_log.read_text()
        assert "init" in log
        assert "-backend-config=" in log
        assert "dev.tfbackend" in log
        assert "-reconfigure" in log

    def test_apply_with_auto_approve_flag(self, invoke, mock_terraform_log):
        result = invoke("apply", "dev", "-auto-approve")
        assert result.exit_code == 0
        log = mock_terraform_log.read_text()
        assert "-auto-approve" in log

    def test_state_list_without_env(self, invoke, mock_terraform_log):
        result = invoke("state", "list")
        assert result.exit_code == 0
        log = mock_terraform_log.read_text()
        assert "state list" in log

    def test_state_with_env(self, invoke, mock_terraform_log):
        result = invoke("state", "dev", "list")
        assert result.exit_code == 0
        log = mock_terraform_log.read_text()
        assert "state list" in log

    def test_validate_without_env(self, invoke, mock_terraform_log):
        result = invoke("validate")
        assert result.exit_code == 0
        log = mock_terraform_log.read_text()
        assert "validate" in log
        assert "-var-file=" not in log

    def test_run_custom_command(self, invoke, mock_terraform_log):
        result = invoke("run", "dev", "workspace", "list")
        assert result.exit_code == 0
        log = mock_terraform_log.read_text()
        assert "workspace list" in log

    def test_default_environment(self, invoke, mock_terraform_log):
        result = invoke("plan")
        assert result.exit_code == 0
        log = mock_terraform_log.read_text()
        assert "dev.tfvars" in log

    def test_missing_environment_fails(self, invoke):
        result = invoke("plan", "missing")
        assert result.exit_code == 1
        assert "not found" in result.stdout.lower() or "not found" in result.stderr.lower()

    def test_env_create(self, invoke, project_dir):
        project, _, _ = project_dir
        result = invoke("env", "create", "qa")
        assert result.exit_code == 0
        assert (project / "vars" / "qa.tfvars").is_file()
        assert (project / "vars" / "qa.tfbackend").is_file()

    def test_env_create_rejects_invalid_name(self, invoke):
        result = invoke("env", "create", "../bad")
        assert result.exit_code == 1

    def test_env_copy(self, invoke, project_dir):
        project, _, _ = project_dir
        result = invoke("env", "copy", "dev", "qa")
        assert result.exit_code == 0
        assert (project / "vars" / "qa.tfvars").is_file()
        content = (project / "vars" / "qa.tfvars").read_text()
        assert 'environment = "qa"' in content or "qa" in content

    def test_config_set_project(self, invoke, project_dir):
        project, _, _ = project_dir
        result = invoke("config", "set", "auto_approve", "true", "--project")
        assert result.exit_code == 0
        config = json.loads((project / ".toffee.json").read_text())
        assert config["auto_approve"] is True

    def test_parallel_plan(self, invoke, mock_terraform_log):
        result = invoke("plan", "dev", "staging", "--parallel")
        assert result.exit_code == 0
        log = mock_terraform_log.read_text()
        assert log.count("plan") == 2
