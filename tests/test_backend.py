"""Tests for backend detection and state identity."""

import sys

import pytest

from toffee.core.backend import (
    UNKNOWN_BACKEND,
    BackendError,
    describe_identity,
    find_backend,
    find_backend_or_unknown,
    same_state,
    settings_from_text,
    state_identity,
)


def _identity(root, text, workspace="default"):
    return state_identity(
        find_backend(str(root)), settings_from_text(text), str(root), workspace
    )


def _write_backend(root, block):
    (root / "main.tf").write_text(f"terraform {{\n  {block}\n}}\n")


def test_s3_identity_uses_bucket_and_key(tmp_path):
    _write_backend(tmp_path, 'backend "s3" {}')

    dev = _identity(
        tmp_path, 'bucket = "b"\nkey = "dev/terraform.tfstate"\nregion = "a"'
    )
    prod = _identity(tmp_path, 'bucket = "b"\nkey = "prod/terraform.tfstate"')
    copy = _identity(
        tmp_path, 'bucket = "b"\nkey = "prod/terraform.tfstate"\nregion = "x"'
    )

    assert dev != prod
    assert prod == copy


def test_workspace_key_prefix_only_matters_outside_default_workspace(tmp_path):
    _write_backend(tmp_path, 'backend "s3" {}')
    first = 'bucket = "b"\nkey = "k"\nworkspace_key_prefix = "one"'
    second = 'bucket = "b"\nkey = "k"\nworkspace_key_prefix = "two"'

    assert _identity(tmp_path, first) == _identity(tmp_path, second)
    assert _identity(tmp_path, first, "blue") != _identity(tmp_path, second, "blue")


def test_block_settings_are_merged_with_environment_settings(tmp_path):
    _write_backend(
        tmp_path, 'backend "s3" {\n    bucket = "b"\n    key = "shared"\n  }'
    )

    assert _identity(tmp_path, 'region = "a"') == _identity(tmp_path, 'region = "b"')
    assert _identity(tmp_path, 'key = "dev"') != _identity(tmp_path, 'key = "prod"')


def test_local_paths_are_normalized(tmp_path):
    _write_backend(tmp_path, "backend local {}")

    assert _identity(tmp_path, 'path = "./state/a.tfstate"') == _identity(
        tmp_path, 'path = "state/../state/a.tfstate"'
    )
    assert _identity(tmp_path, "") == _identity(tmp_path, 'path = "terraform.tfstate"')


@pytest.mark.parametrize(
    "backend_type, same, different",
    [
        ("gcs", 'bucket = "b"\nprefix = "p"', 'bucket = "b"\nprefix = "q"'),
        (
            "azurerm",
            'storage_account_name = "a"\ncontainer_name = "c"\nkey = "k"',
            'storage_account_name = "a"\ncontainer_name = "c"\nkey = "j"',
        ),
        ("consul", 'path = "a"', 'path = "b"'),
        ("http", 'address = "https://x/a"', 'address = "https://x/b"'),
        ("kubernetes", 'secret_suffix = "a"', 'secret_suffix = "b"'),
        ("pg", 'conn_str = "postgres://a"', 'conn_str = "postgres://b"'),
        (
            "remote",
            'organization = "o"\nworkspaces { name = "a" }',
            'organization = "o"\nworkspaces { name = "b" }',
        ),
    ],
)
def test_known_backend_identities(tmp_path, backend_type, same, different):
    _write_backend(tmp_path, f'backend "{backend_type}" {{}}')

    assert _identity(tmp_path, same) == _identity(tmp_path, same + '\nretry_max = "3"')
    assert _identity(tmp_path, same) != _identity(tmp_path, different)


def test_cloud_block_is_detected(tmp_path):
    (tmp_path / "main.tf").write_text(
        'terraform {\n  cloud {\n    organization = "o"\n'
        '    workspaces {\n      name = "app"\n    }\n  }\n}\n'
    )

    backend = find_backend(str(tmp_path))

    assert backend.type == "cloud"
    assert backend.settings["workspaces"] == {"name": "app"}


def test_unknown_backend_ignores_credentials(tmp_path):
    _write_backend(tmp_path, 'backend "custom" {}')

    first = _identity(tmp_path, 'target = "a"\npassword = "one"')
    second = _identity(tmp_path, 'target = "a"\npassword = "two"')

    assert first == second
    assert "one" not in describe_identity(first)
    assert _identity(tmp_path, 'target = "b"') != first


def test_pg_connection_string_is_not_described(tmp_path):
    _write_backend(tmp_path, 'backend "pg" {}')

    identity = _identity(tmp_path, 'conn_str = "postgres://u:hunter2@db"')

    assert "hunter2" not in describe_identity(identity)


def test_override_files_replace_backend(tmp_path):
    _write_backend(tmp_path, 'backend "s3" {}')
    (tmp_path / "backend_override.tf").write_text(
        'terraform {\n  backend "gcs" {}\n}\n'
    )

    assert find_backend(str(tmp_path)).type == "gcs"


def test_tf_json_backend_is_detected(tmp_path):
    (tmp_path / "main.tf.json").write_text(
        '{"terraform": [{"backend": [{"s3": [{"bucket": "b"}]}]}]}'
    )

    backend = find_backend(str(tmp_path))

    assert backend.type == "s3"
    assert backend.settings == {"bucket": "b"}


def test_backend_inside_heredoc_or_string_is_ignored(tmp_path):
    (tmp_path / "main.tf").write_text(
        'locals {\n  doc = <<EOF\nterraform {\n  backend "gcs" {}\n}\nEOF\n'
        '  text = "terraform { backend \\"http\\" {} }"\n}\n'
        'terraform {\n  backend "s3" {}\n}\n'
    )

    assert find_backend(str(tmp_path)).type == "s3"


def test_no_backend_block_is_shared_local_state(tmp_path):
    (tmp_path / "main.tf").write_text('output "x" { value = 1 }\n')

    assert find_backend(str(tmp_path)) is None
    assert _identity(tmp_path, 'path = "a"') == _identity(tmp_path, 'path = "b"')


def test_unreadable_configuration_raises(tmp_path):
    (tmp_path / "main.tf").write_text('terraform {\n  backend "s3" {\n')

    with pytest.raises(BackendError):
        find_backend(str(tmp_path))


def test_unparsable_root_falls_back_to_unknown_backend(tmp_path):
    (tmp_path / "main.tf").write_text('terraform {\n  backend "s3" {\n')

    backend, problem = find_backend_or_unknown(str(tmp_path))

    assert backend is UNKNOWN_BACKEND
    assert "main.tf" in problem


def test_unknown_backend_compares_every_non_credential_setting(tmp_path):
    def identity(text, workspace="default"):
        return state_identity(
            UNKNOWN_BACKEND, settings_from_text(text), str(tmp_path), workspace
        )

    first = identity('bucket = "b"\nkey = "k"\ntoken = "one"')

    assert same_state(first, identity('bucket = "b"\nkey = "k"\ntoken = "two"'))
    assert same_state(first, identity('bucket = "b"\nkey = "k"', "blue"))
    assert not same_state(first, identity('bucket = "b"\nkey = "j"'))
    assert not same_state(first, identity('bucket = "b"\nkey = "k"\nregion = "r"'))
    assert "one" not in describe_identity(first)


def test_local_paths_keep_their_case_for_display(tmp_path):
    _write_backend(tmp_path, "backend local {}")

    identity = _identity(tmp_path, 'path = "State/Dev.tfstate"')

    assert "State/Dev.tfstate" in describe_identity(identity)


@pytest.mark.skipif(
    sys.platform not in ("darwin", "win32"), reason="case-insensitive default"
)
def test_local_paths_compare_case_insensitively(tmp_path):
    _write_backend(tmp_path, "backend local {}")

    assert same_state(
        _identity(tmp_path, 'path = "State/Dev.tfstate"'),
        _identity(tmp_path, 'path = "state/dev.tfstate"'),
    )


def test_non_local_paths_compare_case_sensitively(tmp_path):
    _write_backend(tmp_path, 'backend "consul" {}')

    assert not same_state(
        _identity(tmp_path, 'path = "State/Dev"'),
        _identity(tmp_path, 'path = "state/dev"'),
    )
