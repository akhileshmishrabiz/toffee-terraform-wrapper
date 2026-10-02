"""Unified check command. Behavior is defined in specs/check.md."""

import os
import shlex
import stat
import subprocess
import sys
from pathlib import Path

from toffee.core.checks import (
    format_missing,
    parse_checks,
    plan_steps,
    rerun_command,
    status_style,
    tflint_install_lines,
)

CHECKOV_FAILURE = "Check: CKV_AWS_20: Some bucket is public"


def _log(log_file):
    return log_file.read_text()


def _path_with(bin_dir: Path) -> str:
    """Prefer the fake tools without hiding /bin, which the Terraform mock needs."""
    return os.pathsep.join((str(bin_dir), "/usr/bin", "/bin"))


def _write_tool(directory: Path, name: str, log: Path, stdout: str = "", code: int = 0):
    directory.mkdir(parents=True, exist_ok=True)
    script = directory / name
    lines = [
        "#!/bin/sh",
        f"printf '%s\\n' \"$0 $*\" >> {shlex.quote(str(log))}",
    ]
    if stdout:
        lines.append(f"printf '%s\\n' {shlex.quote(stdout)}")
    lines.append(f"exit {code}")
    script.write_text("\n".join(lines) + "\n")
    script.chmod(script.stat().st_mode | stat.S_IEXEC)


class TestCheckPlan:
    def test_steps_follow_the_spec(self):
        steps = plan_steps(
            "terraform",
            ["-chdir=module"],
            ["dev", "prod"],
            ["vars/dev.tfvars", "vars/prod.tfvars"],
            ["checkov", "tflint"],
            "/work/module",
        )

        assert [step.label for step in steps] == [
            "fmt",
            "dev validate",
            "prod validate",
            "dev checkov",
            "prod checkov",
            "dev tflint",
            "prod tflint",
        ]
        assert steps[0].argv == (
            "terraform",
            "-chdir=module",
            "fmt",
            "-check",
            "-diff",
            "-recursive",
        )
        assert steps[0].cwd is None
        assert steps[0].environment is None
        assert steps[1].argv == ("terraform", "-chdir=module", "validate")
        assert steps[1].environment == "dev"
        assert "--var-file=" not in " ".join(steps[1].argv)
        checkov = steps[3]
        assert checkov.cwd == "/work/module"
        assert checkov.environment is None
        assert checkov.argv == (
            "checkov",
            "-d",
            ".",
            "--framework",
            "terraform",
            "--output",
            "cli",
            "--quiet",
            "--compact",
            "--download-external-modules",
            "false",
            "--skip-path",
            ".terraform",
            "--skip-path",
            ".toffee",
            "--var-file",
            "vars/dev.tfvars",
        )
        assert steps[5].argv == (
            "tflint",
            "--format",
            "compact",
            "--var-file=vars/dev.tfvars",
        )

    def test_parse_preserves_order_and_trims_names(self):
        assert parse_checks(["--checks", " checkov , tflint "]) == ["checkov", "tflint"]
        assert parse_checks(["--checks=tflint"]) == ["tflint"]
        assert parse_checks([]) == []

    def test_parse_rejects_invalid_lists(self):
        for args in (
            ["--checks"],
            ["--checks="],
            ["--checks", "tflint,,checkov"],
            ["--checks", "fmt"],
            ["--checks", "validate"],
            ["--checks", "opa"],
            ["--checks", "tflint,tflint"],
            ["--checks", "tflint", "--checks", "checkov"],
            ["positional"],
        ):
            try:
                parse_checks(args)
            except ValueError:
                continue
            raise AssertionError(f"accepted invalid args: {args}")

    def test_missing_checkov_message_prints_uv_and_pipx(self):
        message = format_missing(
            [("checkov", "checkov")],
            rerun_command(["dev"], [], []),
        )

        assert message == (
            "Error: checkov was not found on PATH.\n"
            "--checks selected it, so this run stopped before any check ran.\n"
            "\n"
            "Install checkov with either command:\n"
            "  uv tool install checkov\n"
            "  pipx install checkov\n"
            "\n"
            "Or run without it:\n"
            "  toffee dev check"
        )

    def test_missing_tflint_uses_the_current_operating_system(self):
        message = format_missing(
            [("tflint", "tflint"), ("checkov", "checkov")],
            rerun_command(["dev", "prod"], ["-chdir=module"], []),
        )

        for line in tflint_install_lines():
            assert line in message
        assert "uv tool install tflint" not in message
        assert "pipx install tflint" not in message
        assert "uv tool install checkov" in message
        assert "pipx install checkov" in message
        assert "Or run without them:\n  toffee dev,prod -chdir=module check" in message

    def test_pass_lines_are_green_and_fail_lines_are_red(self, monkeypatch):
        import io

        from rich.console import Console

        from toffee.commands import check as check_module

        assert status_style("fmt passed") == "green"
        assert status_style("tflint failed with exit code 2") == "red"
        buffer = io.StringIO()
        monkeypatch.setattr(
            check_module,
            "status_console",
            Console(
                file=buffer,
                force_terminal=True,
                soft_wrap=True,
                color_system="standard",
                no_color=False,
                _environ={},
            ),
        )
        check_module.CheckCommands._print_status("fmt passed", indent="  ")
        check_module.CheckCommands._print_status(
            "tflint failed with exit code 2", indent="  "
        )
        output = buffer.getvalue()
        assert "\x1b[32m" in output
        assert "\x1b[31m" in output
        assert "fmt passed" in output
        assert "tflint failed with exit code 2" in output

    def test_tflint_install_commands_follow_the_operating_system(self):
        macos = tflint_install_lines("Darwin", "arm64")
        windows = tflint_install_lines("Windows", "AMD64")
        linux_amd64 = tflint_install_lines("Linux", "x86_64")
        linux_arm64 = tflint_install_lines("Linux", "aarch64")
        go_install = "go install github.com/terraform-linters/tflint@latest"

        assert macos == [
            "Install tflint with:",
            "  brew install terraform-linters/tap/tflint",
            "Or with Go:",
            f"  {go_install}",
        ]
        assert windows == [
            "Install tflint with:",
            "  winget install -e --id TerraformLinters.tflint",
            "Or with Go:",
            f"  {go_install}",
        ]
        assert (
            "  curl -sSLO https://github.com/terraform-linters/tflint/releases/latest/download/tflint_linux_amd64.zip"
            in linux_amd64
        )
        assert "  unzip tflint_linux_amd64.zip" in linux_amd64
        assert "  sudo install -c -v tflint /usr/local/bin/" in linux_amd64
        assert "tflint_linux_arm64.zip" in "\n".join(linux_arm64)
        assert "brew install" not in "\n".join(linux_amd64)
        assert "winget install" not in "\n".join(macos)
        assert go_install in "\n".join(linux_amd64)

    def test_missing_terraform_has_no_rerun_line(self):
        message = format_missing([("terraform", "/opt/tofu")], None)

        assert message == (
            "Error: /opt/tofu was not found.\n"
            "This run stopped before any check ran.\n"
            "\n"
            "/opt/tofu\n"
            "  toffee check runs terraform fmt and terraform validate."
        )
        assert "uv tool" not in message
        assert "Or run without" not in message


class TestCheckCommand:
    def test_default_runs_fmt_and_validate(self, invoke, mock_terraform_log):
        result = invoke("dev", "check")

        assert result.exit_code == 0
        lines = _log(mock_terraform_log).splitlines()
        assert len(lines) == 2
        assert lines[0].startswith("TF_DATA_DIR= ")
        assert lines[0].endswith("fmt -check -diff -recursive")
        assert lines[1].endswith("validate")
        assert lines[1].split()[0].endswith("/.toffee/terraform-data/dev")
        assert "Checks for dev: fmt, validate" in result.stderr
        assert "fmt passed" in result.stderr
        assert "validate passed" in result.stderr
        assert "Summary" in result.stderr
        assert "tflint" not in result.stderr
        assert "checkov" not in result.stderr
        positions = [
            result.stderr.index(label)
            for label in ("\nfmt\n", "\nvalidate\n", "\nSummary\n")
        ]
        assert positions == sorted(positions)

    def test_help_is_toffee_help(self, invoke, mock_terraform_log):
        result = invoke("dev", "check", "--help")

        assert result.exit_code == 0
        assert result.stdout.startswith("Usage: toffee <env>[,<env>...] check")
        assert "--checks" in result.stdout
        assert "tflint,checkov" in result.stdout
        assert "failed checks" in result.stdout
        assert _log(mock_terraform_log) == ""

    def test_help_word_shows_the_same_help(self, invoke, mock_terraform_log):
        result = invoke("dev", "check", "help")

        assert result.exit_code == 0
        assert result.stdout.startswith("Usage: toffee <env>[,<env>...] check")
        assert "--checks" in result.stdout
        assert "TERRAFORM_COMMAND" not in result.stdout
        assert _log(mock_terraform_log) == ""

    def test_singular_check_flag_names_the_option(self, invoke, mock_terraform_log):
        result = invoke("dev", "check", "--check")

        assert result.exit_code == 2
        assert result.stderr.startswith("Usage: toffee <env>[,<env>...] check")
        assert "--checks TOOLS" in result.stderr
        assert "Unknown option '--check'. Use --checks tflint,checkov." in result.stderr
        assert "TERRAFORM_COMMAND" not in result.stderr
        assert _log(mock_terraform_log) == ""

    def test_singular_check_flag_keeps_the_scanner_name(
        self, invoke, mock_terraform_log
    ):
        result = invoke("dev", "check", "--check", "tflint")

        assert result.exit_code == 2
        assert "Use --checks tflint." in result.stderr
        assert "--checks TOOLS" in result.stderr
        assert _log(mock_terraform_log) == ""

    def test_parallel_is_rejected(self, invoke, mock_terraform_log):
        result = invoke("dev", "check", "--parallel")

        assert result.exit_code == 2
        assert result.stderr.startswith("Usage: toffee <env>[,<env>...] check")
        assert "Remove --parallel" in result.stderr
        assert "TERRAFORM_COMMAND" not in result.stderr
        assert _log(mock_terraform_log) == ""

    def test_unknown_check_is_a_usage_error(self, invoke, mock_terraform_log):
        result = invoke("dev", "check", "--checks", "opa")

        assert result.exit_code == 2
        assert result.stderr.startswith("Usage: toffee <env>[,<env>...] check")
        assert "--checks TOOLS" in result.stderr
        assert "tflint and checkov" in result.stderr
        assert _log(mock_terraform_log) == ""

    def test_missing_checkov_stops_before_fmt(
        self, invoke, mock_terraform_log, tmp_path
    ):
        result = invoke(
            "dev",
            "check",
            "--checks",
            "checkov",
            extra_env={"PATH": str(tmp_path)},
        )

        assert result.exit_code == 1
        assert _log(mock_terraform_log) == ""
        assert "uv tool install checkov" in result.stderr
        assert "pipx install checkov" in result.stderr
        assert "Or run without it:\n  toffee dev check" in result.stderr

    def test_missing_tflint_does_not_suggest_python_installers(
        self, invoke, mock_terraform_log, tmp_path
    ):
        result = invoke(
            "dev",
            "-chdir=module",
            "check",
            "--checks",
            "tflint,checkov",
            extra_env={"PATH": str(tmp_path)},
        )

        assert result.exit_code == 1
        assert _log(mock_terraform_log) == ""
        for line in tflint_install_lines():
            assert line in result.stderr
        assert "uv tool install tflint" not in result.stderr
        assert "pipx install tflint" not in result.stderr
        assert "uv tool install checkov" in result.stderr
        assert "toffee dev -chdir=module check" in result.stderr

    def test_missing_terraform_stops_before_fmt(self, invoke, mock_terraform_log):
        result = invoke(
            "dev",
            "check",
            extra_env={"TOFFEE_TERRAFORM_PATH": "/no/such/terraform"},
        )

        assert result.exit_code == 1
        assert "Error: /no/such/terraform was not found." in result.stderr
        assert "on PATH" not in result.stderr
        assert "Or run without" not in result.stderr
        assert _log(mock_terraform_log) == ""

    def test_invalid_environment_runs_nothing(self, invoke, mock_terraform_log):
        result = invoke("qa", "check")

        assert result.exit_code == 1
        assert "not found" in result.stderr.lower()
        assert _log(mock_terraform_log) == ""

    def test_selected_scanners_run_after_terraform(
        self, invoke, mock_terraform_log, tmp_path
    ):
        tool_log = tmp_path / "tools.log"
        bin_dir = tmp_path / "bin"
        _write_tool(bin_dir, "tflint", tool_log)
        _write_tool(bin_dir, "checkov", tool_log)
        result = invoke(
            "dev",
            "check",
            "--checks=checkov,tflint",
            extra_env={"PATH": _path_with(bin_dir)},
        )

        assert result.exit_code == 0
        assert "Checks for dev: fmt, validate, checkov, tflint" in result.stderr
        stderr = result.stderr
        assert (
            stderr.index("\nfmt\n")
            < stderr.index("\nvalidate\n")
            < stderr.index("\ncheckov\n")
            < stderr.index("\ntflint\n")
        )
        tool_lines = tool_log.read_text().splitlines()
        assert len(tool_lines) == 2
        assert "checkov" in tool_lines[0]
        assert "--quiet" in tool_lines[0]
        assert "--compact" in tool_lines[0]
        assert "--framework terraform" in tool_lines[0]
        assert "--var-file vars/dev.tfvars" in tool_lines[0]
        assert tool_lines[1].endswith(
            "tflint --format compact --var-file=vars/dev.tfvars"
        )

    def test_multiple_environments_scan_source_once_per_environment(
        self, invoke, mock_terraform_log, tmp_path
    ):
        tool_log = tmp_path / "tools.log"
        bin_dir = tmp_path / "bin"
        _write_tool(bin_dir, "checkov", tool_log)
        result = invoke(
            "dev,prod",
            "check",
            "--checks",
            "checkov",
            extra_env={"PATH": _path_with(bin_dir)},
        )

        assert result.exit_code == 0
        lines = _log(mock_terraform_log).splitlines()
        assert len([line for line in lines if "fmt -check" in line]) == 1
        validate_lines = [line for line in lines if line.endswith(" validate")]
        assert len(validate_lines) == 2
        assert validate_lines[0].split()[0].endswith("/dev")
        assert validate_lines[1].split()[0].endswith("/prod")
        tool_lines = tool_log.read_text().splitlines()
        assert "--var-file vars/dev.tfvars" in tool_lines[0]
        assert "--var-file vars/prod.tfvars" in tool_lines[1]
        assert "dev checkov" in result.stderr
        assert "prod checkov" in result.stderr
        assert "Checks for dev, prod: fmt, validate, checkov" in result.stderr

    def test_later_checks_still_run_after_a_failure(
        self, invoke, mock_terraform_log, tmp_path, project_dir
    ):
        _project, log_file, env = project_dir
        failing = tmp_path / "terraform-fail.sh"
        failing.write_text(
            "#!/bin/sh\n"
            'printf \'TF_DATA_DIR=%s %s\\n\' "${TF_DATA_DIR:-}" "$*" >> '
            f"{shlex.quote(str(log_file))}\n"
            'if [ "$1" = "validate" ]; then exit 1; fi\n'
            "exit 0\n"
        )
        failing.chmod(0o755)
        tool_log = tmp_path / "tools.log"
        bin_dir = tmp_path / "bin"
        _write_tool(bin_dir, "checkov", tool_log, stdout=CHECKOV_FAILURE, code=1)
        result = invoke(
            "dev",
            "check",
            "--checks",
            "checkov",
            extra_env={
                "PATH": _path_with(bin_dir),
                "TOFFEE_TERRAFORM_PATH": str(failing),
                "MOCK_TF_LOG": env["MOCK_TF_LOG"],
            },
        )

        assert result.exit_code == 1
        lines = _log(mock_terraform_log).splitlines()
        assert any("fmt -check" in line for line in lines)
        assert any(line.endswith(" validate") for line in lines)
        assert tool_log.read_text() != ""
        assert "validate failed with exit code 1" in result.stderr
        assert "checkov failed with exit code 1" in result.stderr

    def test_fmt_status_is_reported_and_normalized(self, invoke, mock_terraform_log):
        result = invoke("dev", "check", extra_env={"MOCK_TF_EXIT": "3"})

        assert result.exit_code == 1
        assert "fmt failed with exit code 3" in result.stderr
        assert "validate failed with exit code 3" in result.stderr

    def test_checkov_stdout_contains_only_the_failing_check(
        self, project_dir, tmp_path
    ):
        project, _log, env = project_dir
        bin_dir = tmp_path / "bin"
        tool_log = tmp_path / "tools.log"
        _write_tool(bin_dir, "checkov", tool_log, stdout=CHECKOV_FAILURE, code=1)
        result = subprocess.run(
            [sys.executable, "-m", "toffee", "dev", "check", "--checks", "checkov"],
            cwd=project,
            env={**os.environ, **env, "PATH": _path_with(bin_dir)},
            capture_output=True,
            text=True,
            check=False,
        )

        assert result.returncode == 1
        assert "fmt passed" in result.stderr
        assert result.stdout == CHECKOV_FAILURE + "\n"
        assert "Passed checks" not in result.stdout
        assert "--quiet" in tool_log.read_text()
        assert "--compact" in tool_log.read_text()
        assert "checkov failed with exit code 1" in result.stderr
