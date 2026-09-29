# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

## [Unreleased]

### Added

- Require an explicit Toffee confirmation before applying to or destroying
  `prod` and `production`, even when automatic approval is enabled, and show a
  credential-safe backend destination before confirmation.
- Add `toffee diff <source> <target>` to compare top-level `.tfvars` and
  `.tfbackend` settings between environments, with sensitive values redacted by
  default.
