"""Tests for simple environment assignment parsing."""

import pytest

from toffee.core.environment_diff import (
    HCLError,
    contains_secret,
    is_sensitive_key,
    read_assignments,
)


def test_read_assignments_handles_scalars_comments_and_collections(tmp_path):
    config = tmp_path / "dev.tfvars"
    config.write_text(
        '# ignored\n'
        'environment = "dev" # inline comment\n'
        'url = "https://example.com/#fragment"\n'
        'enabled = true\n'
        'tags = {\n'
        '  Team = "platform"\n'
        '  Tier = "app"\n'
        '}\n'
    )

    assert read_assignments(str(config)) == {
        "environment": '"dev"',
        "url": '"https://example.com/#fragment"',
        "enabled": "true",
        "tags": '{ Team = "platform" Tier = "app" }',
    }


def test_heredoc_bodies_are_values_not_assignments(tmp_path):
    config = tmp_path / "dev.tfvars"
    config.write_text(
        "script = <<EOF\n"
        "region = \"inside\"\n"
        "# not a comment\n"
        "EOF\n"
        "indented = <<-EOT\n"
        "    body\n"
        "    EOT\n"
        'after = "yes"\n'
    )

    assert read_assignments(str(config)) == {
        "script": '<<EOF\nregion = "inside"\n# not a comment\nEOF',
        "indented": "<<-EOT\n    body\n    EOT",
        "after": '"yes"',
    }


def test_block_comments_are_ignored(tmp_path):
    config = tmp_path / "dev.tfvars"
    config.write_text(
        '/* region = "commented"\n'
        'still = "comment" */\n'
        'region = /* inline */ "real"\n'
    )

    assert read_assignments(str(config)) == {"region": '"real"'}


@pytest.mark.parametrize(
    "content, message",
    [
        ('tags = {\n  a = "b"\nregion = "x"\n', "unterminated value for 'tags'"),
        ("script = <<EOF\nno end\n", "unterminated heredoc <<EOF"),
        ('/* open\nregion = "x"\n', "unterminated comment"),
        ('region = "open\n', "unterminated string"),
    ],
)
def test_unterminated_constructs_are_errors(tmp_path, content, message):
    config = tmp_path / "dev.tfvars"
    config.write_text(content)

    with pytest.raises(HCLError, match=message):
        read_assignments(str(config))


@pytest.mark.parametrize(
    "key",
    [
        "api_token",
        "clientSecret",
        "private_key",
        "password",
        "api_key",
        "apikey",
        "db_pass",
        "passwd",
        "pwd",
        "auth",
        "conn_str",
        "connection_string",
        "database_url",
        "ssh_key",
        "webhook_url",
        "github_pat",
        "AWS_SECRET_ACCESS_KEY",
    ],
)
def test_sensitive_key_detection(key):
    assert is_sensitive_key(key)


@pytest.mark.parametrize(
    "key", ["region", "key", "bucket", "path", "author", "bypass", "kms_key_id"]
)
def test_ordinary_keys_are_not_sensitive(key):
    assert not is_sensitive_key(key)


def test_composite_values_with_sensitive_nested_keys_are_secret():
    assert contains_secret('{ password = "x" }')
    assert contains_secret('[{ name = "a", "api_key" = "b" }]')
    assert contains_secret('{ auth: "x" }')
    assert not contains_secret('{ name = "a", region = "b" }')
    assert not contains_secret('"password"')


def test_url_credentials_are_secret():
    assert contains_secret('"postgres://admin:hunter2@db:5432/app"')
    assert not contains_secret('"https://example.com/path"')
