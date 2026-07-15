#!/usr/bin/env bash

set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
workflow="$repo_root/.github/workflows/validate.yml"

if ! grep -Eq '^permissions:$' "$workflow" || ! grep -Eq '^  contents: read$' "$workflow"; then
  echo "Validation workflow must declare top-level read-only contents permission." >&2
  exit 1
fi

checkout_count="$(grep -Ec '^[[:space:]]+uses: actions/checkout@' "$workflow")"
credential_opt_out_count="$(grep -Ec '^[[:space:]]+persist-credentials: false$' "$workflow")"

if [[ "$checkout_count" -eq 0 || "$credential_opt_out_count" -ne "$checkout_count" ]]; then
  echo "Every validation checkout must disable persisted credentials ($credential_opt_out_count/$checkout_count)." >&2
  exit 1
fi

lint_job="$(sed -n '/^  lint:/,/^  validate:/p' "$workflow")"
validate_job="$(sed -n '/^  validate:/,$p' "$workflow")"

if ! grep -Eq '^      security-events: write$' <<< "$lint_job"; then
  echo "Lint job must receive security-events write permission for SARIF upload." >&2
  exit 1
fi

if grep -Eq '^[[:space:]]+security-events:' <<< "$validate_job"; then
  echo "Validate job must inherit read-only contents permission without security-events write." >&2
  exit 1
fi

upload_count="$(grep -Ec '^[[:space:]]+- name: Upload SARIF' "$workflow")"
safe_upload_count="$(grep -Ec "if: .*github.event.pull_request.head.repo.full_name == github.repository.*github.actor != 'dependabot\[bot\]'" "$workflow")"

if [[ "$upload_count" -eq 0 || "$safe_upload_count" -ne "$upload_count" ]]; then
  echo "Every SARIF upload must skip fork and Dependabot pull requests ($safe_upload_count/$upload_count)." >&2
  exit 1
fi

echo "GitOps validation workflow security contract passed."
