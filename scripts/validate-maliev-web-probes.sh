#!/usr/bin/env bash

set -euo pipefail

for tool in kustomize yq; do
  if ! command -v "$tool" >/dev/null 2>&1; then
    echo "Required tool is not available: $tool" >&2
    exit 1
  fi
done

assert_rendered_value() {
  local manifest="$1"
  local environment="$2"
  local query="$3"
  local expected="$4"
  local description="$5"
  local actual

  actual="$(yq eval-all --unwrapScalar "$query" "$manifest")"
  if [[ "$actual" != "$expected" ]]; then
    echo "Maliev.Web ${environment} ${description}: expected '${expected}', got '${actual}'" >&2
    return 1
  fi
}

temporary_directory="$(mktemp -d)"
trap 'rm -rf "$temporary_directory"' EXIT

container_query='.kind == "Deployment" and .metadata.name == "maliev-web"'

for environment in development staging production; do
  manifest="$temporary_directory/${environment}.yaml"
  kustomize build "3-apps/maliev-web/overlays/${environment}" > "$manifest"

  query_prefix="select(${container_query}) | .spec.template.spec.containers[] | select(.name == \"maliev-web\")"
  assert_rendered_value "$manifest" "$environment" "${query_prefix} | .livenessProbe.httpGet.path" "/web/liveness" "liveness path"
  assert_rendered_value "$manifest" "$environment" "${query_prefix} | .readinessProbe.httpGet.path" "/web/readiness" "readiness path"
  assert_rendered_value "$manifest" "$environment" "${query_prefix} | .startupProbe.httpGet.path" "/web/liveness" "startup path"
  assert_rendered_value "$manifest" "$environment" "${query_prefix} | .startupProbe.periodSeconds" "5" "startup period"
  assert_rendered_value "$manifest" "$environment" "${query_prefix} | .startupProbe.failureThreshold" "24" "startup failure threshold"
done

echo "Maliev.Web rendered probe contract is valid for development, staging, and production."
