"""Tests for CLI argument normalization."""

from toffee.cli_helpers import normalize_envs_and_args


class TestNormalizeEnvsAndArgs:
    def test_moves_flags_from_envs_to_extra_args(self):
        envs, args = normalize_envs_and_args(
            ["dev", "-auto-approve"], ["-target=foo"]
        )
        assert envs == ["dev"]
        assert args == ["-target=foo", "-auto-approve"]

    def test_empty_envs(self):
        envs, args = normalize_envs_and_args(None, ["-refresh-only"])
        assert envs == []
        assert args == ["-refresh-only"]
