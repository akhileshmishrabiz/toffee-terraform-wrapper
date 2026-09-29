#!/usr/bin/env bash
# Mock terraform binary for tests. Logs invocations and exits successfully,
# unless MOCK_TF_EXIT or MOCK_TF_EXIT_<env> (keyed by TF_DATA_DIR) says otherwise.
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

if [[ -n "${MOCK_TF_STDERR:-}" ]]; then
  printf '%s\n' "$MOCK_TF_STDERR" >&2
fi

if [[ "${1:-}" == "plan" ]]; then
  out=""
  previous=""
  for arg in "$@"; do
    case "$arg" in
      -out=*) out="${arg#-out=}" ;;
    esac
    if [[ "$previous" == "-out" ]]; then
      out="$arg"
    fi
    previous="$arg"
  done
  if [[ -n "$out" ]]; then
    printf 'PK\003\004mock plan for %s\n' "${TF_DATA_DIR##*/}" > "$out"
  fi
fi

env_name="${TF_DATA_DIR:-}"
env_name="${env_name##*/}"
exit_name="MOCK_TF_EXIT_${env_name//[^A-Za-z0-9_]/_}"
exit "${!exit_name:-${MOCK_TF_EXIT:-0}}"
