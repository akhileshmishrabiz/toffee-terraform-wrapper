"""Shared pytest fixtures."""

import os
import shutil
import stat
from pathlib import Path

import pytest
from click.testing import CliRunner

from toffee.cli import app

FIXTURES_DIR = Path(__file__).parent / "fixtures"
MOCK_TERRAFORM = FIXTURES_DIR / "mock_terraform.sh"
TERRAFORM_PROJECT = FIXTURES_DIR / "terraform-project"


@pytest.fixture(autouse=True)
def isolated_home(tmp_path_factory, monkeypatch):
    """Keep a developer's ~/.toffee and environment out of every test."""
    home = tmp_path_factory.mktemp("home")
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("USERPROFILE", str(home))
    for name in ("TOFFEE_TERRAFORM_PATH", "TF_WORKSPACE", "TF_DATA_DIR"):
        monkeypatch.delenv(name, raising=False)
    return home


@pytest.fixture
def cli_runner():
    return CliRunner()


@pytest.fixture
def mock_terraform_log(tmp_path):
    log_file = tmp_path / "terraform.log"
    log_file.touch()
    return log_file


@pytest.fixture
def project_dir(tmp_path, mock_terraform_log):
    project = tmp_path / "project"
    shutil.copytree(TERRAFORM_PROJECT, project)

    mock_tf = tmp_path / "mock_terraform.sh"
    shutil.copy2(MOCK_TERRAFORM, mock_tf)
    mock_tf.chmod(mock_tf.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)

    env = os.environ.copy()
    env["MOCK_TF_LOG"] = str(mock_terraform_log)
    env["TOFFEE_TERRAFORM_PATH"] = str(mock_tf)

    return project, mock_terraform_log, env


@pytest.fixture
def invoke(cli_runner, project_dir):
    project, _log_file, env = project_dir

    def _invoke(*args, input=None, extra_env=None):
        previous = os.getcwd()
        os.chdir(project)
        try:
            return cli_runner.invoke(
                app, list(args), env={**env, **(extra_env or {})}, input=input
            )
        finally:
            os.chdir(previous)

    return _invoke


@pytest.fixture
def real_terraform_project(tmp_path):
    project = tmp_path / "real-project"
    shutil.copytree(TERRAFORM_PROJECT, project)
    return project
