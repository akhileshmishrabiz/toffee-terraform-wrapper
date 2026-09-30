"""Tests for environment discovery and validation."""

import os

from toffee.core.environment import EnvironmentManager


class TestEnvironmentManager:
    def test_discover_environments(self, tmp_path):
        vars_dir = tmp_path / "vars"
        vars_dir.mkdir()
        (vars_dir / "dev.tfvars").write_text('environment = "dev"\n')
        (vars_dir / "dev.tfbackend").write_text('path = "dev.tfstate"\n')
        (vars_dir / "prod.tfvars").write_text('environment = "prod"\n')

        manager = EnvironmentManager(vars_dir=str(vars_dir))
        assert manager.get_environment_names() == ["dev", "prod"]

    def test_validate_env_name_rejects_invalid(self):
        invalid_names = [
            "",
            "../evil",
            "bad/name",
            "bad\\name",
            "has space",
            "env",
            "config",
            "diff",
            "info",
            "new",
        ]
        for name in invalid_names:
            valid, _ = EnvironmentManager.validate_env_name(name)
            assert valid is False

    def test_validate_env_name_accepts_valid(self):
        valid, error = EnvironmentManager.validate_env_name("dev-staging_1")
        assert valid is True
        assert error is None

    def test_validate_environment_requires_vars(self, tmp_path):
        vars_dir = tmp_path / "vars"
        vars_dir.mkdir()
        (vars_dir / "dev.tfbackend").write_text('path = "dev.tfstate"\n')

        manager = EnvironmentManager(vars_dir=str(vars_dir))
        valid, error = manager.validate_environment("dev", require_vars=True)
        assert valid is False
        assert "Missing vars file" in error

    def test_create_environment_template(self, tmp_path):
        vars_dir = tmp_path / "vars"
        manager = EnvironmentManager(vars_dir=str(vars_dir))

        success, error = manager.create_environment_template("qa")
        assert success is True
        assert error is None
        assert os.path.isfile(vars_dir / "qa.tfvars")
        assert os.path.isfile(vars_dir / "qa.tfbackend")

    def test_create_environment_rejects_path_traversal(self, tmp_path):
        manager = EnvironmentManager(vars_dir=str(tmp_path / "vars"))
        success, error = manager.create_environment_template("../outside")
        assert success is False
        assert error is not None

    def test_suggest_environment(self, tmp_path):
        vars_dir = tmp_path / "vars"
        vars_dir.mkdir()
        (vars_dir / "dev.tfvars").write_text("")
        (vars_dir / "staging.tfvars").write_text("")

        manager = EnvironmentManager(vars_dir=str(vars_dir))
        assert manager.suggest_environment("de") == "dev"
        assert manager.suggest_environment("stag") == "staging"

    def test_sibling_dir_not_treated_as_inside_vars(self, tmp_path):
        vars_dir = tmp_path / "vars"
        vars_dir.mkdir()
        manager = EnvironmentManager(vars_dir=str(vars_dir))
        vars_dir_real = os.path.realpath(str(vars_dir))

        assert manager._is_safe_env_path("dev", vars_dir_real) is True
        assert manager._is_safe_env_path("../vars-evil/dev", vars_dir_real) is False

    def test_case_conflict_is_detected(self, tmp_path):
        vars_dir = tmp_path / "vars"
        vars_dir.mkdir()
        (vars_dir / "prod.tfbackend").write_text("")
        manager = EnvironmentManager(vars_dir=str(vars_dir))

        assert manager.case_conflict("Prod") == "prod"
        assert manager.case_conflict("prod") is None
        success, error = manager.create_environment_template("PROD")
        assert success is False
        assert "differs only by case" in error

    def test_create_refuses_symlinked_files(self, tmp_path):
        vars_dir = tmp_path / "vars"
        vars_dir.mkdir()
        outside = tmp_path / "outside"
        (vars_dir / "qa.tfvars").symlink_to(outside)
        manager = EnvironmentManager(vars_dir=str(vars_dir))

        success, error = manager.create_environment_template("qa")

        assert success is False
        assert "symlink" in error
        assert not outside.exists()

    def test_refresh_environments(self, tmp_path):
        vars_dir = tmp_path / "vars"
        vars_dir.mkdir()
        manager = EnvironmentManager(vars_dir=str(vars_dir))
        assert manager.get_environment_names() == []

        (vars_dir / "qa.tfvars").write_text("")
        manager.refresh_environments()
        assert manager.get_environment_names() == ["qa"]

    def test_reserved_names_explain_the_rule(self):
        valid, error = EnvironmentManager.validate_env_name("new")
        assert valid is False
        assert "reserved: config, diff, env, info, new" in error
