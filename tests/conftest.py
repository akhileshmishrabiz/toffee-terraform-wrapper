"""Shared pytest fixtures."""

import json
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

    mock_tf = project / "mock_terraform.sh"
    shutil.copy2(MOCK_TERRAFORM, mock_tf)
    mock_tf.chmod(mock_tf.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)

    config_file = project / ".toffee.json"
    config = json.loads(config_file.read_text())
    config["terraform_path"] = str(mock_tf)
    config_file.write_text(json.dumps(config, indent=2))

    env = os.environ.copy()
    env["MOCK_TF_LOG"] = str(mock_terraform_log)

    return project, mock_terraform_log, env


@pytest.fixture
def invoke(cli_runner, project_dir):
    project, _log_file, env = project_dir

    def _invoke(*args, input=None):
        previous = os.getcwd()
        os.chdir(project)
        try:
            return cli_runner.invoke(app, list(args), env=env, input=input)
        finally:
            os.chdir(previous)

    return _invoke


@pytest.fixture
def real_terraform_project(tmp_path):
    project = tmp_path / "real-project"
    shutil.copytree(TERRAFORM_PROJECT, project)
    return project
