"""CLI integration tests using a mock terraform binary."""

import json

import pytest


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

    def test_diff_shows_variable_and_backend_changes(
        self, invoke, mock_terraform_log
    ):
        result = invoke("diff", "dev", "prod")

        assert result.exit_code == 0
        assert "Variables differences" in result.stdout
        assert "environment" in result.stdout
        assert '"dev"' in result.stdout
        assert '"prod"' in result.stdout
        assert "Backend differences" in result.stdout
        assert ".terraform-state/dev/terraform.tfstate" in result.stdout
        assert ".terraform-state/prod/terraform.tfstate" in result.stdout
        assert mock_terraform_log.read_text() == ""

    def test_diff_redacts_sensitive_values(self, invoke, project_dir):
        project, _, _ = project_dir
        dev_vars = project / "vars" / "dev.tfvars"
        prod_vars = project / "vars" / "prod.tfvars"
        dev_vars.write_text(dev_vars.read_text() + '\napi_token = "dev-secret"\n')
        prod_vars.write_text(prod_vars.read_text() + '\napi_token = "prod-secret"\n')

        result = invoke("diff", "dev", "prod")

        assert result.exit_code == 0
        assert "api_token" in result.stdout
        assert "<redacted>" in result.stdout
        assert "dev-secret" not in result.stdout
        assert "prod-secret" not in result.stdout

    def test_diff_can_explicitly_show_sensitive_values(self, invoke, project_dir):
        project, _, _ = project_dir
        dev_vars = project / "vars" / "dev.tfvars"
        prod_vars = project / "vars" / "prod.tfvars"
        dev_vars.write_text(dev_vars.read_text() + '\napi_token = "dev-secret"\n')
        prod_vars.write_text(prod_vars.read_text() + '\napi_token = "prod-secret"\n')

        result = invoke("diff", "dev", "prod", "--show-sensitive")

        assert result.exit_code == 0
        assert '"dev-secret"' in result.stdout
        assert '"prod-secret"' in result.stdout

    def test_diff_rejects_missing_environment(self, invoke):
        result = invoke("diff", "dev", "missing")

        assert result.exit_code == 1
        assert "not found" in result.stderr.lower()

    def test_diff_redacts_composites_with_sensitive_nested_keys(
        self, invoke, project_dir
    ):
        project, _, _ = project_dir
        (project / "vars" / "dev.tfvars").write_text(
            'db = {\n  host = "dev-db"\n  password = "dev-pw"\n}\n'
            'db_pass = "dev-pass"\n'
            'dsn = "postgres://u:dev-url-pw@db/app"\n'
        )
        (project / "vars" / "prod.tfvars").write_text(
            'db = { host = "prod-db", password = "prod-pw" }\n'
            'db_pass = "prod-pass"\n'
            'url = "postgres://u:prod-url-pw@db/app"\n'
        )

        result = invoke("diff", "dev", "prod")

        assert result.exit_code == 0
        for secret in ("dev-pw", "prod-pw", "dev-pass", "prod-pass", "url-pw"):
            assert secret not in result.stdout
        assert result.stdout.count("<redacted>") == 6

    def test_diff_filters_control_and_bidi_characters(self, invoke, project_dir):
        project, _, _ = project_dir
        (project / "vars" / "dev.tfvars").write_text(
            'label = "a\x1b[2Jb\u202ec\x85d"\n'
        )

        result = invoke("diff", "dev", "prod")

        assert result.exit_code == 0
        assert not any(character in result.stdout for character in "\x1b\u202e\x85")
        assert "a\ufffd[2Jb\ufffdc\ufffdd" in result.stdout

    def test_diff_detects_heredoc_differences(self, invoke, project_dir):
        project, _, _ = project_dir
        for env in ("dev", "prod"):
            (project / "vars" / f"{env}.tfvars").write_text(
                f"script = <<EOF\necho {env}\nregion = \"x\"\nEOF\n"
            )

        result = invoke("diff", "dev", "prod")

        assert result.exit_code == 0
        assert "script" in result.stdout
        assert "region" not in result.stdout.replace('region = "x"', "")

    def test_diff_exit_code_option(self, invoke):
        different = invoke("diff", "dev", "prod", "--exit-code")
        same = invoke("diff", "dev", "dev", "--exit-code")
        missing = invoke("diff", "dev", "missing", "--exit-code")

        assert different.exit_code == 1
        assert same.exit_code == 0
        assert missing.exit_code == 2

    def test_diff_reports_unreadable_files_cleanly(self, invoke, project_dir):
        project, _, _ = project_dir
        (project / "vars" / "dev.tfvars").write_bytes(b"region = \"\xff\xfe\"\n")
        (project / "vars" / "prod.tfvars").write_text("tags = {\n")

        result = invoke("diff", "dev", "prod")

        assert result.exit_code == 1
        assert "Cannot read vars/dev.tfvars" in result.stderr
        assert "Traceback" not in result.output

    def test_diff_reports_unterminated_block(self, invoke, project_dir):
        project, _, _ = project_dir
        (project / "vars" / "prod.tfvars").write_text('tags = {\n  a = "b"\n')

        result = invoke("diff", "dev", "prod")

        assert result.exit_code == 1
        assert "unterminated value for 'tags'" in result.stderr

    def test_diff_reports_missing_value_as_parse_error(self, invoke, project_dir):
        project, _, _ = project_dir
        (project / "vars" / "prod.tfvars").write_text('environment = "prod"\nx = \n')

        result = invoke("diff", "dev", "prod", "--exit-code")
        default = invoke("diff", "dev", "prod")

        assert result.exit_code == 2
        assert (
            "Error: Cannot parse vars/prod.tfvars: missing value for 'x' on line 2"
            in result.stderr
        )
        assert "differences" not in result.stdout
        assert default.exit_code == 1
        assert "Traceback" not in default.output

    def test_plan_single_env(self, invoke, mock_terraform_log):
        result = invoke("dev", "plan")
        assert result.exit_code == 0
        log = mock_terraform_log.read_text()
        assert "plan" in log
        assert "-var-file=" in log
        assert "dev.tfvars" in log

    def test_plan_multiple_envs(self, invoke, mock_terraform_log):
        result = invoke("dev,staging", "plan")
        assert result.exit_code == 0
        lines = mock_terraform_log.read_text().splitlines()
        assert len(lines) == 2
        log = "\n".join(lines)
        assert "dev.tfvars" in log
        assert "staging.tfvars" in log

    def test_duplicate_targets_are_deduplicated(self, invoke, mock_terraform_log):
        result = invoke("dev,dev", "plan")
        assert result.exit_code == 0
        log = mock_terraform_log.read_text()
        assert log.count("plan") == 1

    def test_init_includes_backend_config(self, invoke, mock_terraform_log):
        result = invoke("dev", "init")
        assert result.exit_code == 0
        log = mock_terraform_log.read_text()
        assert "init" in log
        assert "-backend-config=" in log
        assert "dev.tfbackend" in log
        assert "-reconfigure" in log

    def test_apply_with_auto_approve_flag(self, invoke, mock_terraform_log):
        result = invoke("dev", "apply", "-auto-approve")
        assert result.exit_code == 0
        log = mock_terraform_log.read_text()
        assert "-auto-approve" in log

    def test_prod_apply_requires_confirmation(self, invoke, mock_terraform_log):
        result = invoke("prod", "apply", input="n\n")
        assert result.exit_code == 1
        assert "apply changes to PROD" in result.stderr
        assert "Environment: prod" in result.stderr
        assert (
            "Backend: local://.terraform-state/prod/terraform.tfstate"
            in result.stderr
        )
        assert mock_terraform_log.read_text() == ""

    def test_auto_approve_does_not_bypass_prod_confirmation(
        self, invoke, mock_terraform_log
    ):
        result = invoke("prod", "apply", "-auto-approve", input="n\n")
        assert result.exit_code == 1
        assert "Continue? [y/N]" in result.stderr
        assert mock_terraform_log.read_text() == ""

    def test_project_auto_approve_does_not_bypass_prod_confirmation(
        self, invoke, mock_terraform_log
    ):
        config_result = invoke(
            "config", "set", "auto_approve", "true", "--project"
        )
        assert config_result.exit_code == 0

        result = invoke("prod", "apply", input="n\n")

        assert result.exit_code == 1
        assert "Continue? [y/N]" in result.stderr
        assert mock_terraform_log.read_text() == ""

    def test_confirmed_prod_apply_runs(self, invoke, mock_terraform_log):
        result = invoke("prod", "apply", "-auto-approve", input="y\n")
        assert result.exit_code == 0
        log = mock_terraform_log.read_text()
        assert "apply" in log
        assert "-auto-approve" in log
        assert "prod.tfvars" in log

    def test_state_list(self, invoke, mock_terraform_log):
        result = invoke("dev", "state", "list")
        assert result.exit_code == 0
        log = mock_terraform_log.read_text()
        assert "state list" in log

    def test_state_show(self, invoke, mock_terraform_log):
        result = invoke("dev", "state", "show", "null_resource.example")
        assert result.exit_code == 0
        log = mock_terraform_log.read_text()
        assert "state show null_resource.example" in log

    def test_validate_with_env(self, invoke, mock_terraform_log):
        result = invoke("dev", "validate")
        assert result.exit_code == 0
        log = mock_terraform_log.read_text()
        assert "validate" in log
        assert "-var-file=" not in log

    def test_run_custom_command(self, invoke, mock_terraform_log):
        result = invoke("dev", "workspace", "list")
        assert result.exit_code == 0
        log = mock_terraform_log.read_text()
        assert "workspace list" in log

    def test_environment_is_required(self, invoke):
        result = invoke("plan")
        assert result.exit_code != 0

    def test_missing_environment_fails(self, invoke):
        result = invoke("missing", "plan")
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

    @pytest.mark.parametrize("command", [["copy", "dev", "qa"], ["create", "qa"]])
    def test_env_created_paths_are_not_wrapped(self, invoke, project_dir, command):
        project, _, _ = project_dir
        vars_dir = project / ("environment-files-" * 6)
        vars_dir.mkdir()
        for name in ("dev.tfvars", "dev.tfbackend"):
            (vars_dir / name).write_text((project / "vars" / name).read_text())
        (project / ".toffee.json").write_text(
            json.dumps({"vars_dir": vars_dir.name, "terraform_path": "terraform"})
        )

        result = invoke("env", *command)

        assert result.exit_code == 0, result.output
        assert len(str(vars_dir / "qa.tfvars")) > 80
        lines = result.stdout.splitlines()
        assert f"  - {vars_dir / 'qa.tfvars'}" in lines

    def test_config_set_project(self, invoke, project_dir):
        project, _, _ = project_dir
        result = invoke("config", "set", "auto_approve", "true", "--project")
        assert result.exit_code == 0
        config = json.loads((project / ".toffee.json").read_text())
        assert config["auto_approve"] is True

    def test_parallel_plan(self, invoke, mock_terraform_log):
        result = invoke("dev,staging", "plan", "--parallel")
        assert result.exit_code == 0
        assert len(mock_terraform_log.read_text().splitlines()) == 2

    def test_parallel_plan_groups_output_per_env(self, invoke):
        result = invoke("dev,staging", "plan", "--parallel")
        assert result.exit_code == 0
        assert "dev succeeded" in result.stderr
        assert "staging succeeded" in result.stderr

    def test_destroy_abort_returns_nonzero(self, invoke, mock_terraform_log):
        result = invoke("dev", "destroy", input="n\n")
        assert result.exit_code == 1
        assert "aborted" in result.stderr.lower()
        assert "This will destroy resources in: dev" in result.stderr
        assert "destroy resources" not in result.stdout
        assert "Do you want to continue" not in result.stdout
        assert "destroy" not in mock_terraform_log.read_text()

    def test_destroy_confirmed_runs(self, invoke, mock_terraform_log):
        result = invoke("dev", "destroy", input="y\n")
        assert result.exit_code == 0
        log = mock_terraform_log.read_text()
        assert "destroy" in log
        assert "-auto-approve" in log

    def test_auto_approve_does_not_bypass_prod_destroy_confirmation(
        self, invoke, mock_terraform_log
    ):
        result = invoke("prod", "destroy", "-auto-approve", input="n\n")
        assert result.exit_code == 1
        assert "destroy resources in PROD" in result.stderr
        assert mock_terraform_log.read_text() == ""

    def test_project_auto_approve_does_not_bypass_prod_destroy_confirmation(
        self, invoke, mock_terraform_log
    ):
        config_result = invoke(
            "config", "set", "auto_approve", "true", "--project"
        )
        assert config_result.exit_code == 0

        result = invoke("prod", "destroy", input="n\n")

        assert result.exit_code == 1
        assert "destroy resources in PROD" in result.stderr
        assert mock_terraform_log.read_text() == ""

    def test_auto_approve_config_not_duplicated(self, invoke, project_dir, mock_terraform_log):
        project, _, _ = project_dir
        invoke("config", "set", "auto_approve", "true", "--project")
        result = invoke("dev", "apply", "-auto-approve")
        assert result.exit_code == 0
        log = mock_terraform_log.read_text()
        assert log.count("-auto-approve") == 1

    def test_terraform_flags_are_passed_through(self, invoke, mock_terraform_log):
        result = invoke("dev", "apply", "-auto-approve", "-var", "region=us-east-1")
        assert result.exit_code == 0
        log = mock_terraform_log.read_text()
        assert "-auto-approve" in log
        assert "-var region=us-east-1" in log
        assert "dev.tfvars" in log

    def test_targets_have_isolated_terraform_data_dirs(
        self, invoke, mock_terraform_log
    ):
        result = invoke("dev,staging", "plan", "--parallel")
        assert result.exit_code == 0
        lines = mock_terraform_log.read_text().splitlines()
        assert any(".toffee/terraform-data/dev plan" in line for line in lines)
        assert any(".toffee/terraform-data/staging plan" in line for line in lines)

    def test_unknown_command_is_passed_without_var_file(
        self, invoke, mock_terraform_log
    ):
        result = invoke("dev", "future-command", "--new-flag", "value")
        assert result.exit_code == 0
        log = mock_terraform_log.read_text()
        assert "future-command --new-flag value" in log
        assert "-var-file=" not in log

    def test_all_targets_are_validated_before_execution(
        self, invoke, mock_terraform_log
    ):
        result = invoke("dev,missing", "plan")
        assert result.exit_code == 1
        assert mock_terraform_log.read_text() == ""

    def test_destroy_target_is_validated_before_confirmation(
        self, invoke, mock_terraform_log
    ):
        result = invoke("missing", "destroy")

        assert result.exit_code == 1
        assert "not found" in result.stderr
        assert "Do you want to continue?" not in result.output
        assert mock_terraform_log.read_text() == ""

    def test_parallel_init_is_safely_serialized(self, invoke, mock_terraform_log):
        result = invoke("dev,staging", "init", "--parallel")
        assert result.exit_code == 0
        assert "serialized" in result.stderr
        assert mock_terraform_log.read_text().count(" init ") == 2

    def test_parallel_interactive_apply_is_rejected(
        self, invoke, mock_terraform_log
    ):
        result = invoke("dev,staging", "apply", "--parallel")
        assert result.exit_code == 1
        assert "requires -auto-approve" in result.stderr
        assert mock_terraform_log.read_text() == ""

    def test_json_output_is_not_polluted_by_wrapper_status(self, invoke, capfd):
        result = invoke("dev", "output", "-json")
        captured = capfd.readouterr()
        assert result.exit_code == 0
        assert captured.out == '{"environment":"mock"}\n'
        assert "Running:" in result.stderr

    def test_global_terraform_options_are_preserved(
        self, invoke, mock_terraform_log
    ):
        result = invoke("dev", "-compact-warnings", "plan")
        assert result.exit_code == 0
        log = mock_terraform_log.read_text()
        assert "-compact-warnings plan -var-file=" in log

    def test_quoted_targets_allow_whitespace(self, invoke, mock_terraform_log):
        result = invoke("dev, staging", "plan")
        assert result.exit_code == 0
        assert len(mock_terraform_log.read_text().splitlines()) == 2
