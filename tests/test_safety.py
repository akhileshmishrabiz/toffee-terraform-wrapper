"""Tests for production safety helpers."""

from toffee.core.safety import describe_backend, is_protected_environment


def test_default_protected_environment_names_are_case_insensitive():
    assert is_protected_environment("prod")
    assert is_protected_environment("PRODUCTION")
    assert not is_protected_environment("staging")


def test_describe_s3_backend(tmp_path):
    (tmp_path / "main.tf").write_text(
        'terraform {\n  backend "s3" {}\n}\n'
    )
    backend_file = tmp_path / "prod.tfbackend"
    backend_file.write_text(
        'bucket = "company-tf-state"\n'
        'key = "prod/terraform.tfstate"\n'
        'region = "us-east-1"\n'
    )

    assert (
        describe_backend(str(tmp_path), str(backend_file))
        == "s3://company-tf-state/prod/terraform.tfstate"
    )


def test_backend_summary_does_not_expose_unrecognized_values(tmp_path):
    (tmp_path / "main.tf").write_text(
        'terraform {\n  backend "custom" {}\n}\n'
    )
    backend_file = tmp_path / "prod.tfbackend"
    backend_file.write_text('password = "do-not-print"\n')

    summary = describe_backend(str(tmp_path), str(backend_file))

    assert summary == "custom (configured by prod.tfbackend)"
    assert "do-not-print" not in summary


def test_backend_summary_does_not_expose_credentials(tmp_path):
    (tmp_path / "main.tf").write_text(
        'terraform {\n  backend "s3" {}\n}\n'
    )
    backend_file = tmp_path / "prod.tfbackend"
    backend_file.write_text(
        'bucket = "company-tf-state"\n'
        'key = "prod/terraform.tfstate"\n'
        'access_key = "AKIA-DO-NOT-PRINT"\n'
        'secret_key = "super-secret"\n'
        'token = "also-secret"\n'
    )

    summary = describe_backend(str(tmp_path), str(backend_file))

    assert summary == "s3://company-tf-state/prod/terraform.tfstate"
    assert "AKIA" not in summary
    assert "super-secret" not in summary
    assert "also-secret" not in summary


def test_backend_summary_rejects_control_characters(tmp_path):
    (tmp_path / "main.tf").write_text(
        'terraform {\n  backend "s3" {}\n}\n'
    )
    backend_file = tmp_path / "prod.tfbackend"
    backend_file.write_text('bucket = "company\x1b[31m-secret"\n')

    summary = describe_backend(str(tmp_path), str(backend_file))

    assert summary == "s3:// (destination not configured)"
    assert "\x1b" not in summary
