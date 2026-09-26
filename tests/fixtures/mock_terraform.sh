#!/usr/bin/env bash
# Mock terraform binary for tests. Logs invocations and exits successfully.
set -euo pipefail

LOG_FILE="${MOCK_TF_LOG:-/dev/null}"
printf 'TF_DATA_DIR=%s %s\n' "${TF_DATA_DIR:-}" "$*" >> "$LOG_FILE"

if [[ "${1:-}" == "-version" ]]; then
  echo "Terraform v1.5.7"
  echo "on darwin_amd64"
  exit 0
fi

if [[ "${1:-}" == "output" && "$*" == *"-json"* ]]; then
  printf '{"environment":"mock"}\n'
fi

case "${1:-}" in
  init|plan|apply|destroy|validate|fmt|output|refresh|state|workspace|import|graph|providers|version|test|console|show|get|login|force-unlock|taint|untaint)
    exit 0
    ;;
  *)
    exit 0
    ;;
esac
