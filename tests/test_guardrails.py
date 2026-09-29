"""Protected-environment, saved-plan, and state-isolation guardrails."""

import json
import os

import pytest


def _log(log_file):
    return log_file.read_text()


def _set_project_config(project, **values):
    config_file = project / ".toffee.json"
    config = json.loads(config_file.read_text())
    config.update(values)
    config_file.write_text(json.dumps(config))


class TestProtectedPrompt:
    @pytest.mark.parametrize("empty", ["", " ", "\t"])
    def test_empty_argument_is_rejected_before_routing(
        self, invoke, mock_terraform_log, empty
    ):
        result = invoke("prod", empty, "apply", "-auto-approve", input="y\n")

        assert result.exit_code == 2
        assert "Empty or whitespace-only arguments" in result.stderr
        assert _log(mock_terraform_log) == ""

    def test_empty_argument_after_command_is_rejected(
        self, invoke, mock_terraform_log
    ):
        result = invoke("dev", "plan", "", input="y\n")

        assert result.exit_code == 2
        assert _log(mock_terraform_log) == ""

    def test_protected_target_later_in_list_is_confirmed(
        self, invoke, mock_terraform_log
    ):
        result = invoke("dev,prod", "apply", "-auto-approve", input="n\n")

        assert result.exit_code == 1
        assert "apply changes to dev, PROD" in result.stderr
        assert "Environment: prod" in result.stderr
        assert _log(mock_terraform_log) == ""

    def test_parallel_does_not_skip_protected_confirmation(
        self, invoke, mock_terraform_log
    ):
        result = invoke(
            "dev,prod", "apply", "-auto-approve", "--parallel", input="n\n"
        )

        assert result.exit_code == 1
        assert "Continue? [y/N]" in result.stderr
        assert _log(mock_terraform_log) == ""

    def test_confirmed_parallel_protected_apply_runs(
        self, invoke, mock_terraform_log
    ):
        result = invoke(
            "dev,prod", "apply", "-auto-approve", "--parallel", input="y\n"
        )

        assert result.exit_code == 0
        assert len(_log(mock_terraform_log).splitlines()) == 2

    @pytest.mark.parametrize("stdin", ["", None])
    def test_closed_stdin_aborts(self, invoke, mock_terraform_log, stdin):
        result = invoke("prod", "apply", "-auto-approve", input=stdin)

        assert result.exit_code == 1
        assert "aborted" in result.stderr.lower()
        assert _log(mock_terraform_log) == ""

    def test_piped_yes_is_accepted(self, invoke, mock_terraform_log):
        result = invoke("prod", "apply", input="y\n")

        assert result.exit_code == 0
        assert " apply " in _log(mock_terraform_log)

    def test_case_variant_of_protected_name_is_protected(
        self, invoke, project_dir, mock_terraform_log
    ):
        project, _, _ = project_dir
        (project / "vars" / "PRODUCTION.tfvars").write_text('environment = "p"\n')
        (project / "vars" / "PRODUCTION.tfbackend").write_text(
            'path = ".terraform-state/production/terraform.tfstate"\n'
        )

        result = invoke("PRODUCTION", "apply", "-auto-approve", input="n\n")

        assert result.exit_code == 1
        assert "apply changes to PRODUCTION" in result.stderr
        assert _log(mock_terraform_log) == ""

    def test_configured_protected_environments_are_added(
        self, invoke, project_dir, mock_terraform_log
    ):
        project, _, _ = project_dir
        _set_project_config(project, protected_environments=["Staging"])

        staging = invoke("staging", "apply", "-auto-approve", input="n\n")
        prod = invoke("prod", "apply", "-auto-approve", input="n\n")

        assert staging.exit_code == 1
        assert "apply changes to STAGING" in staging.stderr
        assert prod.exit_code == 1
        assert _log(mock_terraform_log) == ""

    def test_invalid_protected_environments_fail_closed(
        self, invoke, project_dir, mock_terraform_log
    ):
        project, _, _ = project_dir
        _set_project_config(project, protected_environments="staging")

        result = invoke("staging", "apply", "-auto-approve")

        assert result.exit_code == 1
        assert "protected_environments must be a list" in result.stderr
        assert _log(mock_terraform_log) == ""

    def test_config_set_rejects_list_setting(self, invoke):
        result = invoke(
            "config", "set", "protected_environments", "staging", "--project"
        )

        assert result.exit_code == 1
        assert "Edit it in .toffee.json" in result.output

    @pytest.mark.parametrize(
        "args",
        [
            ["refresh"],
            ["import", "null_resource.example", "id"],
            ["taint", "null_resource.example"],
            ["untaint", "null_resource.example"],
            ["force-unlock", "1234"],
            ["test"],
            ["state", "rm", "null_resource.example"],
            ["state", "mv", "a", "b"],
            ["state", "push", "terraform.tfstate"],
            ["state", "replace-provider", "a", "b"],
            ["workspace", "delete", "old"],
            ["apply", "-destroy"],
            ["apply", "--destroy=true", "-auto-approve"],
        ],
    )
    def test_state_changing_commands_are_protected(
        self, invoke, mock_terraform_log, args
    ):
        result = invoke("prod", *args, input="n\n")

        assert result.exit_code == 1
        assert "Continue? [y/N]" in result.stderr
        assert _log(mock_terraform_log) == ""

    @pytest.mark.parametrize(
        "args", [["plan"], ["state", "list"], ["workspace", "list"], ["output"]]
    )
    def test_read_only_commands_do_not_prompt(
        self, invoke, mock_terraform_log, args
    ):
        result = invoke("prod", *args)

        assert result.exit_code == 0
        assert "Continue?" not in result.stderr
        assert len(_log(mock_terraform_log).splitlines()) == 1

    def test_mixed_destroy_prompt_lists_every_target(
        self, invoke, mock_terraform_log
    ):
        result = invoke("dev,prod", "destroy", input="n\n")

        assert result.exit_code == 1
        assert "destroy resources in dev, PROD" in result.stderr
        assert "Environment: dev" in result.stderr
        assert "Environment: prod" in result.stderr
        assert _log(mock_terraform_log) == ""


class TestDestroyConfirmation:
    def test_apply_destroy_does_not_receive_config_auto_approve(
        self, invoke, project_dir, mock_terraform_log
    ):
        project, _, _ = project_dir
        _set_project_config(project, auto_approve=True)

        result = invoke("dev", "apply", "-destroy", input="n\n")

        assert result.exit_code == 1
        assert "This will destroy resources in: dev" in result.stderr
        assert result.stdout == ""
        assert _log(mock_terraform_log) == ""

    def test_confirmed_apply_destroy_is_auto_approved(
        self, invoke, mock_terraform_log
    ):
        result = invoke("dev", "apply", "-destroy", input="y\n")

        assert result.exit_code == 0
        assert "apply -var-file=" in _log(mock_terraform_log)
        assert "-auto-approve -destroy" in _log(mock_terraform_log)

    def test_explicit_auto_approve_skips_non_protected_destroy_prompt(
        self, invoke, mock_terraform_log
    ):
        result = invoke("dev", "destroy", "--auto-approve")

        assert result.exit_code == 0
        assert "Do you want to continue?" not in result.stderr

    def test_auto_approve_false_still_prompts(self, invoke, mock_terraform_log):
        result = invoke("dev", "destroy", "-auto-approve=false", input="n\n")

        assert result.exit_code == 1
        assert _log(mock_terraform_log) == ""


class TestSavedPlans:
    def _record(self, project, plan="tfplan"):
        return json.loads((project / f"{plan}.toffee.json").read_text())

    def test_plan_out_records_environment(self, invoke, project_dir):
        project, _, _ = project_dir

        result = invoke("prod", "plan", "-out=tfplan")

        assert result.exit_code == 0
        record = self._record(project)
        assert record["environment"] == "prod"
        assert len(record["sha256"]) == 64

    def test_plan_out_space_form_is_recorded(self, invoke, project_dir):
        project, _, _ = project_dir

        assert invoke("dev", "plan", "-out", "dev.tfplan").exit_code == 0
        assert self._record(project, "dev.tfplan")["environment"] == "dev"

    def test_prod_plan_cannot_be_applied_through_dev(
        self, invoke, project_dir, mock_terraform_log
    ):
        assert invoke("prod", "plan", "-out=tfplan").exit_code == 0

        result = invoke("dev", "apply", "tfplan", input="y\n")

        assert result.exit_code == 1
        assert "was created for environment 'prod', not 'dev'" in result.stderr
        assert " apply" not in _log(mock_terraform_log)

    def test_prod_plan_applied_to_prod_is_confirmed(
        self, invoke, mock_terraform_log
    ):
        assert invoke("prod", "plan", "-out=tfplan").exit_code == 0

        declined = invoke("prod", "apply", "tfplan", input="n\n")
        accepted = invoke("prod", "apply", "tfplan", input="y\n")

        assert declined.exit_code == 1
        assert "apply changes to PROD" in declined.stderr
        assert accepted.exit_code == 0
        apply_line = _log(mock_terraform_log).splitlines()[-1]
        assert apply_line.endswith("apply tfplan")

    def test_modified_plan_is_refused(self, invoke, project_dir, mock_terraform_log):
        project, _, _ = project_dir
        assert invoke("dev", "plan", "-out=tfplan").exit_code == 0
        (project / "tfplan").write_bytes(b"PK\x03\x04something else")

        result = invoke("dev", "apply", "tfplan")

        assert result.exit_code == 1
        assert "changed after Toffee recorded it" in result.stderr
        assert " apply" not in _log(mock_terraform_log)

    def test_corrupt_record_is_refused(self, invoke, project_dir, mock_terraform_log):
        project, _, _ = project_dir
        (project / "tfplan").write_bytes(b"PK\x03\x04plan")
        (project / "tfplan.toffee.json").write_text("{not json")

        result = invoke("dev", "apply", "tfplan")

        assert result.exit_code == 1
        assert "Cannot verify saved plan" in result.stderr
        assert _log(mock_terraform_log) == ""

    def test_unrecorded_plan_requires_confirmation_when_project_has_prod(
        self, invoke, project_dir, mock_terraform_log
    ):
        project, _, _ = project_dir
        (project / "manual.tfplan").write_bytes(b"PK\x03\x04plan")

        closed = invoke("dev", "apply", "manual.tfplan", input="")
        accepted = invoke("dev", "apply", "manual.tfplan", input="y\n")

        assert closed.exit_code == 1
        assert "cannot verify which environment" in closed.stderr
        assert "Continue? [y/N]" in closed.stderr
        assert accepted.exit_code == 0
        assert _log(mock_terraform_log).splitlines()[-1].endswith(
            "apply manual.tfplan"
        )

    def test_unrecorded_plan_without_protected_environments_runs(
        self, invoke, project_dir, mock_terraform_log
    ):
        project, _, _ = project_dir
        for name in ("prod.tfvars", "prod.tfbackend"):
            (project / "vars" / name).unlink()
        (project / "manual.tfplan").write_bytes(b"PK\x03\x04plan")

        result = invoke("dev", "apply", "manual.tfplan")

        assert result.exit_code == 0
        assert "Continue?" not in result.stderr

    def test_failed_plan_removes_stale_record(
        self, invoke, project_dir, mock_terraform_log
    ):
        project, _, _ = project_dir
        assert invoke("prod", "plan", "-out=tfplan").exit_code == 0

        failed = invoke(
            "dev", "plan", "-out=tfplan", extra_env={"MOCK_TF_EXIT": "1"}
        )
        result = invoke("dev", "apply", "tfplan", input="n\n")

        assert failed.exit_code == 1
        assert not (project / "tfplan.toffee.json").exists()
        assert result.exit_code == 1
        assert "cannot verify which environment" in result.stderr

    def test_detailed_exitcode_changes_still_record_plan(self, invoke, project_dir):
        project, _, _ = project_dir

        result = invoke(
            "dev",
            "plan",
            "-detailed-exitcode",
            "-out=tfplan",
            extra_env={"MOCK_TF_EXIT": "2"},
        )

        assert result.exit_code == 2
        assert self._record(project)["environment"] == "dev"

    def test_multi_target_plan_out_is_rejected(self, invoke, mock_terraform_log):
        result = invoke("dev,staging", "plan", "-out=tfplan")

        assert result.exit_code == 1
        assert "overwrite the previous plan" in result.stderr
        assert _log(mock_terraform_log) == ""

    def test_multi_target_saved_plan_apply_is_rejected(
        self, invoke, project_dir, mock_terraform_log
    ):
        project, _, _ = project_dir
        (project / "tfplan").write_bytes(b"PK\x03\x04plan")

        result = invoke("dev,staging", "apply", "tfplan", "--parallel")

        assert result.exit_code == 1
        assert "single environment" in result.stderr
        assert _log(mock_terraform_log) == ""

    def test_saved_plan_is_resolved_against_chdir(
        self, invoke, project_dir, mock_terraform_log
    ):
        project, _, _ = project_dir
        sub = project / "sub"
        sub.mkdir()
        (sub / "main.tf").write_text('terraform {\n  backend "local" {}\n}\n')
        (sub / "tfplan").write_bytes(b"PK\x03\x04plan")
        (sub / "tfplan.toffee.json").write_text(
            json.dumps({"environment": "prod", "sha256": "0" * 64})
        )

        result = invoke("dev", "-chdir=sub", "apply", "tfplan")

        assert result.exit_code == 1
        assert "created for environment 'prod'" in result.stderr
        assert _log(mock_terraform_log) == ""


class TestStateIsolation:
    def test_shared_backend_state_is_refused(
        self, invoke, project_dir, mock_terraform_log
    ):
        project, _, _ = project_dir
        (project / "vars" / "staging.tfbackend").write_text(
            'path = "./.terraform-state/prod/terraform.tfstate"\n'
        )

        result = invoke("staging", "destroy", "-auto-approve")

        assert result.exit_code == 1
        assert "'staging' and 'prod' would share Terraform state" in result.stderr
        assert _log(mock_terraform_log) == ""

    def test_unaffected_environment_still_runs(
        self, invoke, project_dir, mock_terraform_log
    ):
        project, _, _ = project_dir
        (project / "vars" / "staging.tfbackend").write_text(
            'path = ".terraform-state/prod/terraform.tfstate"\n'
        )

        assert invoke("dev", "plan").exit_code == 0

    def test_symlinked_backend_file_is_refused(
        self, invoke, project_dir, mock_terraform_log
    ):
        project, _, _ = project_dir
        staging = project / "vars" / "staging.tfbackend"
        staging.unlink()
        staging.symlink_to("prod.tfbackend")

        result = invoke("staging", "plan")

        assert result.exit_code == 1
        assert "resolves to the same file as" in result.stderr
        assert "(environment 'prod')" in result.stderr
        assert _log(mock_terraform_log) == ""

    def test_missing_backend_block_means_shared_default_state(
        self, invoke, project_dir, mock_terraform_log
    ):
        project, _, _ = project_dir
        main = project / "main.tf"
        main.write_text(main.read_text().replace('backend "local" {}', ""))

        result = invoke("dev", "plan")

        assert result.exit_code == 1
        assert "No backend block was found" in result.stderr
        assert _log(mock_terraform_log) == ""

    def test_selected_workspace_separates_state(
        self, invoke, project_dir, mock_terraform_log
    ):
        project, _, _ = project_dir
        (project / "vars" / "staging.tfbackend").write_text(
            'path = ".terraform-state/prod/terraform.tfstate"\n'
        )
        data_dir = project / ".toffee" / "terraform-data" / "staging"
        data_dir.mkdir(parents=True)
        (data_dir / "environment").write_text("staging")

        assert invoke("staging", "plan").exit_code == 0


class TestEnvironmentCopySafety:
    def test_copy_refuses_case_variant_of_existing_environment(
        self, invoke, project_dir
    ):
        project, _, _ = project_dir
        before = (project / "vars" / "prod.tfbackend").read_text()

        result = invoke("env", "copy", "dev", "Prod")

        assert result.exit_code == 1
        assert "differs only by case from existing environment 'prod'" in (
            result.stderr
        )
        assert (project / "vars" / "prod.tfbackend").read_text() == before

    def test_create_refuses_case_variant(self, invoke, project_dir):
        result = invoke("env", "create", "STAGING")

        assert result.exit_code == 1
        assert "differs only by case" in result.stderr

    def test_copy_rewrites_only_exact_references(self, invoke, project_dir):
        project, _, _ = project_dir
        (project / "vars" / "dev.tfvars").write_text(
            "# dev settings\n"
            'environment = "dev"\n'
            'region_name = "dev-eu"\n'
            'domain = "api.dev.example.com"\n'
            "dev = true\n"
            'tags = { Env = "dev" }\n'
        )
        (project / "vars" / "dev.tfbackend").write_text(
            'path = "state/dev/dev.tfstate"\n'
        )

        result = invoke("env", "copy", "dev", "qa")

        assert result.exit_code == 0
        assert (project / "vars" / "qa.tfvars").read_text() == (
            "# dev settings\n"
            'environment = "qa"\n'
            'region_name = "dev-eu"\n'
            'domain = "api.dev.example.com"\n'
            "dev = true\n"
            'tags = { Env = "qa" }\n'
        )
        assert (project / "vars" / "qa.tfbackend").read_text() == (
            'path = "state/qa/qa.tfstate"\n'
        )
        assert 'vars/qa.tfvars:2: "dev" -> "qa"' in result.stdout
        assert "Review the copied files" in result.stdout

    def test_copy_rewrites_backend_segments_without_slashes(
        self, invoke, project_dir
    ):
        project, _, _ = project_dir
        (project / "vars" / "prod.tfbackend").write_text(
            'path = "prod/terraform.tfstate"\n'
        )

        result = invoke("env", "copy", "prod", "qa")

        assert result.exit_code == 0
        assert (project / "vars" / "qa.tfbackend").read_text() == (
            'path = "qa/terraform.tfstate"\n'
        )

    def test_copy_refuses_colliding_state_before_writing(
        self, invoke, project_dir
    ):
        project, _, _ = project_dir
        (project / "vars" / "dev.tfbackend").write_text(
            'path = "state/shared.tfstate"\n'
        )

        result = invoke("env", "copy", "dev", "qa")

        assert result.exit_code == 1
        assert "'qa' and 'dev' would share Terraform state" in result.stderr
        assert "Nothing was written" in result.stderr
        assert not (project / "vars" / "qa.tfvars").exists()
        assert not (project / "vars" / "qa.tfbackend").exists()

    def test_copy_refuses_symlinked_target(self, invoke, project_dir, tmp_path):
        project, _, _ = project_dir
        outside = tmp_path / "outside.txt"
        outside.write_text("keep me\n")
        (project / "vars" / "qa.tfvars").symlink_to(outside)

        result = invoke("env", "copy", "dev", "qa", input="y\n")

        assert result.exit_code == 1
        assert "Refusing to write through symlink" in result.stderr
        assert outside.read_text() == "keep me\n"

    def test_copy_lists_only_written_files(self, invoke, project_dir):
        project, _, _ = project_dir
        (project / "vars" / "solo.tfvars").write_text('environment = "solo"\n')

        result = invoke("env", "copy", "solo", "qa")

        assert result.exit_code == 0
        assert "qa.tfvars" in result.stdout
        assert "qa.tfbackend" not in result.stdout
        assert not (project / "vars" / "qa.tfbackend").exists()

    def test_copy_overwrite_prompt_defaults_to_no(self, invoke, project_dir):
        project, _, _ = project_dir
        before = (project / "vars" / "staging.tfvars").read_text()

        result = invoke("env", "copy", "dev", "staging", input="")

        assert result.exit_code == 1
        assert (project / "vars" / "staging.tfvars").read_text() == before

    def test_copy_leaves_no_temporary_files(self, invoke, project_dir):
        project, _, _ = project_dir

        assert invoke("env", "copy", "dev", "qa").exit_code == 0
        assert not [
            name for name in os.listdir(project / "vars") if name.endswith(".tmp")
        ]
