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


def test_backend_summary_filters_control_and_format_characters(tmp_path):
    (tmp_path / "main.tf").write_text(
        'terraform {\n  backend "s3" {}\n}\n'
    )
    backend_file = tmp_path / "prod.tfbackend"
    backend_file.write_text(
        'bucket = "company\x1b[31m-state"\nkey = "a\u202eb\x9bc/\\u001b"\n'
    )

    summary = describe_backend(str(tmp_path), str(backend_file))

    assert summary == "s3://company\ufffd[31m-state/a\ufffdb\ufffdc/\ufffd"
    assert not any(character in summary for character in "\x1b\u202e\x9b")


def test_extra_protected_names_are_additive_and_case_insensitive():
    assert is_protected_environment("Staging", ["staging"])
    assert is_protected_environment("prod", ["staging"])
    assert not is_protected_environment("dev", ["staging"])


def test_backend_label_may_be_unquoted_and_comments_are_ignored(tmp_path):
    (tmp_path / "a.tf").write_text(
        '# terraform {\n#   backend "gcs" {}\n# }\n'
        '/* terraform { backend "azurerm" {} } */\n'
    )
    (tmp_path / "b.tf").write_text("terraform {\n  backend s3 {}\n}\n")
    backend_file = tmp_path / "prod.tfbackend"
    backend_file.write_text('bucket = "state"\nkey = "prod.tfstate"\n')

    assert (
        describe_backend(str(tmp_path), str(backend_file))
        == "s3://state/prod.tfstate"
    )


def test_backend_summary_reads_tf_json(tmp_path):
    (tmp_path / "main.tf.json").write_text(
        '{"terraform": {"backend": {"gcs": {"bucket": "state"}}}}'
    )
    backend_file = tmp_path / "prod.tfbackend"
    backend_file.write_text('prefix = "prod"\n')

    assert describe_backend(str(tmp_path), str(backend_file)) == "gs://state/prod"


def test_backend_summary_never_prints_pg_connection_string(tmp_path):
    (tmp_path / "main.tf").write_text('terraform {\n  backend "pg" {}\n}\n')
    backend_file = tmp_path / "prod.tfbackend"
    backend_file.write_text('conn_str = "postgres://user:hunter2@db/state"\n')

    summary = describe_backend(str(tmp_path), str(backend_file))

    assert "hunter2" not in summary
    assert summary == "pg (schema terraform_remote_state)"
