"""Execution behavior: parallel output, exit codes, signals, and argv display."""

import os
import signal
import subprocess
import sys
import time

import pytest

from toffee.core.executor import run_parallel


def _log(log_file):
    return log_file.read_text()


class TestParallel:
    def test_parallel_stdout_is_raw_and_separate_from_stderr(self, invoke):
        long_line = "x" * 200
        result = invoke(
            "dev,staging",
            "output",
            "-json",
            "--parallel",
            extra_env={
                "MOCK_TF_STDOUT": f":ok: {long_line}\\n",
                "MOCK_TF_STDERR": "a warning",
            },
        )

        assert result.exit_code == 0
        line = f'{{"environment":"mock"}}\n:ok: {long_line}\n'
        assert result.stdout == line * 2
        assert result.stderr.count("a warning") == 2
        assert "dev succeeded" in result.stderr

    def test_parallel_output_with_invalid_utf8_does_not_crash(self, invoke):
        result = invoke(
            "dev,staging",
            "plan",
            "--parallel",
            extra_env={"MOCK_TF_STDOUT": "bad \\0377 byte\\n"},
        )

        assert result.exit_code == 0
        assert result.stdout_bytes.count(b"bad \xff byte\n") == 2

    def test_parallel_adds_input_false(self, invoke, mock_terraform_log):
        result = invoke("dev,staging", "plan", "--parallel")

        assert result.exit_code == 0
        lines = _log(mock_terraform_log).splitlines()
        assert all("-input=false" in line for line in lines)

    def test_parallel_respects_user_input_flag(self, invoke, mock_terraform_log):
        result = invoke("dev,staging", "plan", "-input=true", "--parallel")

        assert result.exit_code == 0
        assert "-input=false" not in _log(mock_terraform_log)

    def test_sequential_does_not_add_input_false(self, invoke, mock_terraform_log):
        assert invoke("dev,staging", "plan").exit_code == 0
        assert "-input=false" not in _log(mock_terraform_log)

    @pytest.mark.parametrize("args", [["destroy"], ["apply", "-destroy"]])
    def test_parallel_destroy_requires_auto_approve(
        self, invoke, mock_terraform_log, args
    ):
        result = invoke("dev,staging", *args, "--parallel", input="y\n")

        assert result.exit_code == 1
        assert "Parallel destroy requires -auto-approve" in result.stderr
        assert _log(mock_terraform_log) == ""

    def test_parallel_destroy_with_auto_approve_runs(self, invoke, mock_terraform_log):
        result = invoke("dev,staging", "destroy", "-auto-approve", "--parallel")

        assert result.exit_code == 0
        assert len(_log(mock_terraform_log).splitlines()) == 2

    @pytest.mark.parametrize("flag", ["--auto-approve", "-auto-approve=true"])
    def test_parallel_apply_accepts_auto_approve_variants(
        self, invoke, mock_terraform_log, flag
    ):
        result = invoke("dev,staging", "apply", flag, "--parallel")

        assert result.exit_code == 0

    def test_parallel_apply_rejects_auto_approve_false(
        self, invoke, mock_terraform_log
    ):
        result = invoke("dev,staging", "apply", "-auto-approve=false", "--parallel")

        assert result.exit_code == 1
        assert _log(mock_terraform_log) == ""

    def test_parallel_children_get_closed_stdin(self, tmp_path):
        reader = [sys.executable, "-c", "import sys; print(repr(sys.stdin.read()))"]

        [(code, stdout, _stderr)] = run_parallel([(reader, None)])

        assert code == 0
        assert stdout.strip() == b"''"


class TestExitCodes:
    def test_sequential_detailed_exitcode_continues_after_changes(
        self, invoke, mock_terraform_log
    ):
        result = invoke(
            "dev,staging",
            "plan",
            "-detailed-exitcode",
            extra_env={"MOCK_TF_EXIT_dev": "2"},
        )

        assert result.exit_code == 2
        assert len(_log(mock_terraform_log).splitlines()) == 2
        assert "succeeded with changes present" in result.stderr

    def test_sequential_failure_wins_over_changes(self, invoke, mock_terraform_log):
        result = invoke(
            "dev,staging",
            "plan",
            "-detailed-exitcode",
            extra_env={"MOCK_TF_EXIT_dev": "2", "MOCK_TF_EXIT_staging": "1"},
        )

        assert result.exit_code == 1
        assert len(_log(mock_terraform_log).splitlines()) == 2

    def test_parallel_failure_is_not_masked_by_changes(self, invoke):
        result = invoke(
            "dev,staging",
            "plan",
            "-detailed-exitcode",
            "--parallel",
            extra_env={"MOCK_TF_EXIT_dev": "1", "MOCK_TF_EXIT_staging": "2"},
        )

        assert result.exit_code == 1
        assert "dev failed with exit code 1" in result.stderr
        assert "staging succeeded with changes present" in result.stderr

    def test_without_detailed_exitcode_two_is_a_failure(
        self, invoke, mock_terraform_log
    ):
        result = invoke("dev,staging", "plan", extra_env={"MOCK_TF_EXIT_dev": "2"})

        assert result.exit_code == 2
        assert len(_log(mock_terraform_log).splitlines()) == 1


class TestArgvHandling:
    def test_help_is_passed_to_terraform(self, invoke, mock_terraform_log):
        result = invoke("dev", "plan", "--help")

        assert result.exit_code == 0
        assert "Usage: toffee" not in result.output
        assert (
            _log(mock_terraform_log)
            .rstrip()
            .endswith("plan -var-file=vars/dev.tfvars --help")
        )

    def test_running_line_is_not_rich_markup(self, invoke, mock_terraform_log):
        result = invoke("dev", "plan", "-var", "cidrs=[/]")

        assert result.exit_code == 0
        assert "'cidrs=<redacted>'" in result.stderr
        assert "-var cidrs=[/]" in _log(mock_terraform_log)

    def test_running_line_redacts_inline_backend_values(self, invoke):
        result = invoke("dev", "init", "-backend-config=secret_key=hunter2")

        assert result.exit_code == 0
        assert "hunter2" not in result.output
        assert "-backend-config=secret_key=<redacted>" in result.stderr

    def test_supplemental_backend_config_keeps_env_backend(
        self, invoke, mock_terraform_log
    ):
        result = invoke("dev", "init", "-backend-config=workspace_dir=ws")

        assert result.exit_code == 0
        assert (
            "init -backend-config=vars/dev.tfbackend -reconfigure "
            "-backend-config=workspace_dir=ws" in _log(mock_terraform_log)
        )

    def test_auto_approve_is_inserted_before_positionals(
        self, invoke, project_dir, mock_terraform_log
    ):
        assert (
            invoke("config", "set", "auto_approve", "true", "--project").exit_code == 0
        )

        assert invoke("dev", "apply", "-target", "a.b").exit_code == 0
        assert invoke("dev", "apply", "-auto-approve=false", input="").exit_code == 0

        lines = _log(mock_terraform_log).splitlines()
        assert lines[0].endswith(
            "apply -var-file=vars/dev.tfvars -auto-approve -target a.b"
        )
        assert lines[1].endswith("apply -var-file=vars/dev.tfvars -auto-approve=false")


SLOW_TERRAFORM = """\
#!{python}
import os, signal, sys, time
ready, marker = os.environ["SLOW_TF_READY"], os.environ["SLOW_TF_MARKER"]

def stop(signum, frame):
    time.sleep(0.5)
    with open(marker, "w") as f:
        f.write(signal.Signals(signum).name)
    sys.exit(7)

signal.signal(signal.SIGINT, stop)
signal.signal(signal.SIGTERM, stop)
open(ready, "w").close()
time.sleep(30)
sys.exit(0)
"""


@pytest.mark.skipif(sys.platform == "win32", reason="POSIX signals")
class TestSignals:
    @pytest.fixture
    def slow_project(self, project_dir, tmp_path):
        project, _, env = project_dir
        script = tmp_path / "slow-terraform"
        script.write_text(SLOW_TERRAFORM.format(python=sys.executable))
        script.chmod(0o755)
        env = {
            **env,
            "TOFFEE_TERRAFORM_PATH": str(script),
            "SLOW_TF_READY": str(tmp_path / "ready"),
            "SLOW_TF_MARKER": str(tmp_path / "marker"),
        }
        return project, env, tmp_path

    def _start(self, project, env, *args):
        return subprocess.Popen(
            [sys.executable, "-m", "toffee", *args],
            cwd=project,
            env=env,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            start_new_session=True,
        )

    def _wait_ready(self, tmp_path):
        deadline = time.monotonic() + 15
        while not (tmp_path / "ready").exists():
            assert time.monotonic() < deadline, "terraform stand-in did not start"
            time.sleep(0.05)

    @pytest.mark.parametrize(
        "args", [["dev", "plan"], ["dev,staging", "plan", "--parallel"]]
    )
    def test_ctrl_c_waits_for_terraform_to_finish(self, slow_project, args):
        project, env, tmp_path = slow_project
        process = self._start(project, env, *args)
        self._wait_ready(tmp_path)
        time.sleep(0.2)

        os.killpg(process.pid, signal.SIGINT)
        stdout, stderr = process.communicate(timeout=20)

        assert process.returncode == 7
        assert (tmp_path / "marker").read_text() == "SIGINT"
        assert b"Traceback" not in stderr
        assert b"KeyboardInterrupt" not in stderr

    def test_sigterm_is_forwarded(self, slow_project):
        project, env, tmp_path = slow_project
        process = self._start(project, env, "dev", "plan")
        self._wait_ready(tmp_path)

        process.send_signal(signal.SIGTERM)
        _stdout, stderr = process.communicate(timeout=20)

        assert process.returncode == 7
        assert (tmp_path / "marker").read_text() == "SIGTERM"
        assert b"Traceback" not in stderr
