"""Protected-environment, saved-plan, and state-isolation guardrails."""

import json
import os
import stat
import sys

import pytest

from toffee.core import plans


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

    def test_empty_argument_after_command_is_rejected(self, invoke, mock_terraform_log):
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
        result = invoke("dev,prod", "apply", "-auto-approve", "--parallel", input="n\n")

        assert result.exit_code == 1
        assert "Continue? [y/N]" in result.stderr
        assert _log(mock_terraform_log) == ""

    def test_confirmed_parallel_protected_apply_runs(self, invoke, mock_terraform_log):
        result = invoke("dev,prod", "apply", "-auto-approve", "--parallel", input="y\n")

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
        "args",
        [
            ["state", "-lock-timeout=1s", "rm", "null_resource.example"],
            ["workspace", "-no-color", "delete", "old"],
        ],
    )
    def test_options_before_mutating_subcommand_cannot_bypass_prompt(
        self, invoke, mock_terraform_log, args
    ):
        result = invoke("prod", *args, input="n\n")

        assert result.exit_code == 1
        assert "Continue? [y/N]" in result.stderr
        assert _log(mock_terraform_log) == ""

    @pytest.mark.parametrize("args", [["apply", "--help"], ["state", "rm", "--help"]])
    def test_help_for_mutating_commands_does_not_prompt(
        self, invoke, mock_terraform_log, args
    ):
        result = invoke("prod", *args)

        assert result.exit_code == 0
        assert "Continue?" not in result.stderr
        assert len(_log(mock_terraform_log).splitlines()) == 1

    @pytest.mark.parametrize(
        "args", [["plan"], ["state", "list"], ["workspace", "list"], ["output"]]
    )
    def test_read_only_commands_do_not_prompt(self, invoke, mock_terraform_log, args):
        result = invoke("prod", *args)

        assert result.exit_code == 0
        assert "Continue?" not in result.stderr
        assert len(_log(mock_terraform_log).splitlines()) == 1

    def test_mixed_destroy_prompt_lists_every_target(self, invoke, mock_terraform_log):
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
        assert "destroy resources" not in result.stdout
        assert "Do you want to continue" not in result.stdout
        assert _log(mock_terraform_log) == ""

    def test_confirmed_apply_destroy_is_auto_approved(self, invoke, mock_terraform_log):
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

    def test_prod_plan_applied_to_prod_is_confirmed(self, invoke, mock_terraform_log):
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
        assert "cannot be verified: it has no Toffee record" in closed.stderr
        assert "Continue? [y/N]" in closed.stderr
        assert accepted.exit_code == 0
        assert _log(mock_terraform_log).splitlines()[-1].endswith("apply manual.tfplan")

    def test_unrecorded_plan_without_protected_environments_fails_closed(
        self, invoke, project_dir, mock_terraform_log
    ):
        project, _, _ = project_dir
        for name in ("prod.tfvars", "prod.tfbackend"):
            (project / "vars" / name).unlink()
        (project / "manual.tfplan").write_bytes(b"PK\x03\x04plan")

        result = invoke("dev", "apply", "manual.tfplan", input="")

        assert result.exit_code == 1
        assert "cannot be verified" in result.stderr
        assert "Continue? [y/N]" in result.stderr
        assert " apply " not in _log(mock_terraform_log)

    def test_failed_plan_removes_stale_record(
        self, invoke, project_dir, mock_terraform_log
    ):
        project, _, _ = project_dir
        assert invoke("prod", "plan", "-out=tfplan").exit_code == 0

        failed = invoke("dev", "plan", "-out=tfplan", extra_env={"MOCK_TF_EXIT": "1"})
        result = invoke("dev", "apply", "tfplan", input="n\n")

        assert failed.exit_code == 1
        assert not (project / "tfplan.toffee.json").exists()
        assert result.exit_code == 1
        assert "cannot be verified" in result.stderr

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
        plans.write_record(str(sub / "tfplan"), "prod")

        result = invoke("dev", "-chdir=sub", "apply", "tfplan")

        assert result.exit_code == 1
        assert "created for environment 'prod'" in result.stderr
        assert _log(mock_terraform_log) == ""

    def test_record_is_signed_with_private_user_key(
        self, invoke, project_dir, isolated_home
    ):
        project, _, _ = project_dir

        assert invoke("dev", "plan", "-out=tfplan").exit_code == 0

        key_file = isolated_home / ".toffee" / "plan-signing.key"
        assert stat.S_IMODE(key_file.stat().st_mode) == 0o600
        assert len(self._record(project)["signature"]) == 64
        assert (
            key_file.read_text().strip()
            not in (project / "tfplan.toffee.json").read_text()
        )

    def test_signing_key_is_reused(self, invoke, isolated_home):
        assert invoke("dev", "plan", "-out=a.tfplan").exit_code == 0
        key = (isolated_home / ".toffee" / "plan-signing.key").read_text()
        assert invoke("dev", "plan", "-out=b.tfplan").exit_code == 0

        assert (isolated_home / ".toffee" / "plan-signing.key").read_text() == key

    def test_forged_record_requires_confirmation(
        self, invoke, project_dir, mock_terraform_log
    ):
        project, _, _ = project_dir
        assert invoke("prod", "plan", "-out=tfplan").exit_code == 0
        record = self._record(project)
        record["environment"] = "dev"
        (project / "tfplan.toffee.json").write_text(json.dumps(record))

        result = invoke("dev", "apply", "tfplan", input="")

        assert result.exit_code == 1
        assert "tfplan cannot be verified" in result.stderr
        assert "not signed with this user's plan-signing key" in result.stderr
        assert "Continue? [y/N]" in result.stderr
        assert " apply" not in _log(mock_terraform_log)

    @pytest.mark.parametrize("signature", [None, "", "0" * 64, "é" * 64, 7])
    def test_unsigned_or_badly_signed_record_is_not_trusted(
        self, invoke, project_dir, mock_terraform_log, signature
    ):
        project, _, _ = project_dir
        assert invoke("dev", "plan", "-out=tfplan").exit_code == 0
        record = self._record(project)
        if signature is None:
            del record["signature"]
        else:
            record["signature"] = signature
        (project / "tfplan.toffee.json").write_text(json.dumps(record))

        result = invoke("dev", "apply", "tfplan", input="")

        assert result.exit_code == 1
        assert "cannot be verified" in result.stderr
        assert "Continue? [y/N]" in result.stderr
        assert " apply" not in _log(mock_terraform_log)

    def test_record_from_another_key_is_not_trusted(
        self, invoke, project_dir, isolated_home, mock_terraform_log
    ):
        assert invoke("dev", "plan", "-out=tfplan").exit_code == 0
        (isolated_home / ".toffee" / "plan-signing.key").write_text("ab" * 32)

        result = invoke("dev", "apply", "tfplan", input="")

        assert result.exit_code == 1
        assert "not signed with this user's plan-signing key" in result.stderr
        assert " apply" not in _log(mock_terraform_log)

    def test_missing_key_makes_record_unverified(
        self, invoke, project_dir, isolated_home, mock_terraform_log
    ):
        assert invoke("dev", "plan", "-out=tfplan").exit_code == 0
        (isolated_home / ".toffee" / "plan-signing.key").unlink()

        result = invoke("dev", "apply", "tfplan", input="")

        assert result.exit_code == 1
        assert "plan-signing key is unavailable" in result.stderr
        assert " apply" not in _log(mock_terraform_log)
        assert not (isolated_home / ".toffee" / "plan-signing.key").exists()

    @pytest.mark.skipif(os.name != "posix", reason="POSIX permissions")
    def test_key_readable_by_others_is_not_trusted(
        self, invoke, project_dir, isolated_home, mock_terraform_log
    ):
        assert invoke("dev", "plan", "-out=tfplan").exit_code == 0
        (isolated_home / ".toffee" / "plan-signing.key").chmod(0o644)

        result = invoke("dev", "apply", "tfplan", input="")

        assert result.exit_code == 1
        assert "accessible by other users" in result.stderr
        assert " apply" not in _log(mock_terraform_log)

    def test_signed_record_without_protected_environments_runs(
        self, invoke, project_dir, mock_terraform_log
    ):
        project, _, _ = project_dir
        for name in ("prod.tfvars", "prod.tfbackend"):
            (project / "vars" / name).unlink()
        assert invoke("dev", "plan", "-out=tfplan").exit_code == 0

        result = invoke("dev", "apply", "tfplan")

        assert result.exit_code == 0
        assert "Continue?" not in result.stderr

    @pytest.mark.skipif(os.geteuid() == 0, reason="root ignores file permissions")
    def test_unwritable_home_leaves_plan_unrecorded(
        self, invoke, project_dir, isolated_home, mock_terraform_log
    ):
        project, _, _ = project_dir
        isolated_home.chmod(stat.S_IRUSR | stat.S_IXUSR)
        try:
            planned = invoke("dev", "plan", "-out=tfplan")
            applied = invoke("dev", "apply", "tfplan", input="")
        finally:
            isolated_home.chmod(stat.S_IRWXU)

        assert planned.exit_code == 0
        assert "Could not record the plan's environment" in planned.stderr
        assert not (project / "tfplan.toffee.json").exists()
        assert applied.exit_code == 1
        assert "it has no Toffee record" in applied.stderr
        assert " apply" not in _log(mock_terraform_log)


class TestStateIsolation:
    def test_init_inline_backend_override_cannot_select_peer_state(
        self, invoke, mock_terraform_log
    ):
        result = invoke(
            "dev",
            "init",
            "-backend-config=path=.terraform-state/prod/terraform.tfstate",
        )

        assert result.exit_code == 1
        assert "would share Terraform state" in result.stderr
        assert _log(mock_terraform_log) == ""

    def test_init_backend_override_file_cannot_select_peer_state(
        self, invoke, project_dir, mock_terraform_log
    ):
        project, _, _ = project_dir
        (project / "override.tfbackend").write_text(
            'path = ".terraform-state/prod/terraform.tfstate"\n'
        )

        result = invoke("dev", "init", "-backend-config=override.tfbackend")

        assert result.exit_code == 1
        assert "would share Terraform state" in result.stderr
        assert _log(mock_terraform_log) == ""

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

    @pytest.mark.parametrize(
        "args",
        [
            ["fmt", "-check"],
            ["validate"],
            ["version"],
            ["-version"],
            ["get"],
            ["modules", "-json"],
            ["metadata", "functions", "-json"],
            ["providers", "lock"],
            ["providers", "mirror", "mirror-dir"],
            ["logout"],
            ["plan", "-help"],
            ["-help"],
            ["apply", "-auto-approve", "--help"],
            ["state", "list", "-h"],
        ],
    )
    def test_stateless_commands_run_without_a_backend_block(
        self, invoke, project_dir, mock_terraform_log, args
    ):
        project, _, _ = project_dir
        main = project / "main.tf"
        main.write_text(main.read_text().replace('backend "local" {}', ""))

        result = invoke("dev", *args)

        assert result.exit_code == 0, result.output
        assert "would share Terraform state" not in result.stderr
        assert len(_log(mock_terraform_log).splitlines()) == 1

    @pytest.mark.parametrize(
        "args",
        [
            ["plan"],
            ["init"],
            ["output"],
            ["console"],
            ["providers"],
            ["providers", "schema", "-json"],
            ["workspace", "list"],
            ["some-future-command"],
        ],
    )
    def test_state_commands_are_refused_without_a_backend_block(
        self, invoke, project_dir, mock_terraform_log, args
    ):
        project, _, _ = project_dir
        main = project / "main.tf"
        main.write_text(main.read_text().replace('backend "local" {}', ""))

        result = invoke("dev", *args)

        assert result.exit_code == 1
        assert "No backend block was found" in result.stderr
        assert _log(mock_terraform_log) == ""

    def test_root_syntax_error_does_not_block_stateless_commands(
        self, invoke, project_dir, mock_terraform_log
    ):
        project, _, _ = project_dir
        (project / "broken.tf").write_text('resource "null_resource" "x" {\n')

        result = invoke("dev", "validate")

        assert result.exit_code == 0
        assert result.stderr.count("Warning") == 0
        assert " validate" in _log(mock_terraform_log)

    def test_root_syntax_error_compares_backend_assignments(
        self, invoke, project_dir, mock_terraform_log
    ):
        project, _, _ = project_dir
        (project / "broken.tf").write_text('resource "null_resource" "x" {\n')

        result = invoke("dev", "plan")

        assert result.exit_code == 0
        assert "Cannot parse the root module" in result.stderr
        assert "broken.tf" in result.stderr
        assert " plan " in _log(mock_terraform_log)

    def test_root_syntax_error_still_refuses_identical_backend_settings(
        self, invoke, project_dir, mock_terraform_log
    ):
        project, _, _ = project_dir
        (project / "broken.tf").write_text('resource "null_resource" "x" {\n')
        (project / "vars" / "staging.tfbackend").write_text(
            'path = ".terraform-state/prod/terraform.tfstate"\npassword = "differs"\n'
        )

        result = invoke("staging", "plan")

        assert result.exit_code == 1
        assert "'staging' and 'prod' would share Terraform state" in result.stderr
        assert "differs" not in result.stderr
        assert _log(mock_terraform_log) == ""

    def test_root_syntax_error_prompt_shows_unknown_backend(
        self, invoke, project_dir, mock_terraform_log
    ):
        project, _, _ = project_dir
        (project / "broken.tf").write_text('resource "null_resource" "x" {\n')

        result = invoke("prod", "apply", input="")

        assert result.exit_code == 1
        assert "Backend: unknown (could not parse configuration)" in result.stderr
        assert _log(mock_terraform_log) == ""

    def test_unparsable_peer_backend_is_ignored_with_warning(
        self, invoke, project_dir, mock_terraform_log
    ):
        project, _, _ = project_dir
        (project / "vars" / "prod.tfbackend").write_text('path = "unterminated\n')

        result = invoke("dev", "plan")

        assert result.exit_code == 0
        assert "Warning: Ignoring vars/prod.tfbackend" in result.stderr
        assert " plan " in _log(mock_terraform_log)

    def test_unparsable_target_backend_is_refused_for_state_commands(
        self, invoke, project_dir, mock_terraform_log
    ):
        project, _, _ = project_dir
        (project / "vars" / "dev.tfbackend").write_text("path =\n")

        refused = invoke("dev", "plan")
        validated = invoke("dev", "validate")

        assert refused.exit_code == 1
        assert "Cannot verify that environments use separate state" in (refused.stderr)
        assert "missing value for 'path'" in refused.stderr
        assert validated.exit_code == 0
        assert _log(mock_terraform_log).splitlines()[0].endswith("validate")

    def test_shared_state_error_keeps_path_case(
        self, invoke, project_dir, mock_terraform_log
    ):
        project, _, _ = project_dir
        for env in ("staging", "prod"):
            (project / "vars" / f"{env}.tfbackend").write_text(
                'path = "State/Shared.tfstate"\n'
            )

        result = invoke("staging", "plan")

        assert result.exit_code == 1
        assert "State/Shared.tfstate" in result.stderr
        assert os.path.realpath(project) in result.stderr

    @pytest.mark.skipif(
        sys.platform not in ("darwin", "win32"), reason="case-insensitive default"
    )
    def test_local_paths_differing_by_case_share_state(
        self, invoke, project_dir, mock_terraform_log
    ):
        project, _, _ = project_dir
        (project / "vars" / "staging.tfbackend").write_text(
            'path = ".terraform-state/PROD/terraform.tfstate"\n'
        )

        result = invoke("staging", "plan")

        assert result.exit_code == 1
        assert ".terraform-state/PROD/terraform.tfstate" in result.stderr
        assert _log(mock_terraform_log) == ""


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

    def test_copy_rewrites_backend_segments_without_slashes(self, invoke, project_dir):
        project, _, _ = project_dir
        (project / "vars" / "prod.tfbackend").write_text(
            'path = "prod/terraform.tfstate"\n'
        )

        result = invoke("env", "copy", "prod", "qa")

        assert result.exit_code == 0
        assert (project / "vars" / "qa.tfbackend").read_text() == (
            'path = "qa/terraform.tfstate"\n'
        )

    def test_copy_refuses_colliding_state_before_writing(self, invoke, project_dir):
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

    def test_copy_refuses_partial_source_environment(self, invoke, project_dir):
        project, _, _ = project_dir
        (project / "vars" / "solo.tfvars").write_text('environment = "solo"\n')

        result = invoke("env", "copy", "solo", "qa")

        assert result.exit_code == 1
        assert "incomplete" in result.stderr
        assert not (project / "vars" / "qa.tfvars").exists()
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
