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

echo "GitOps validation workflow security contract passed."
