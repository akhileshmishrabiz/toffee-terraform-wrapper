"""Tests for simple environment assignment parsing."""

from toffee.core.environment_diff import is_sensitive_key, read_assignments


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


def test_sensitive_key_detection():
    assert is_sensitive_key("api_token")
    assert is_sensitive_key("clientSecret")
    assert is_sensitive_key("private_key")
    assert not is_sensitive_key("region")
