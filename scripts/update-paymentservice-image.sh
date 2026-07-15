#!/usr/bin/env bash

set -euo pipefail

usage() {
  echo "Usage: $0 <development|staging|production> <environment image repository> <sha256 digest>" >&2
}

if [[ "$#" -ne 3 ]]; then
  usage
  exit 2
fi

environment="$1"
image="$2"
digest="$3"
repo_root="${MALIEV_GITOPS_ROOT:-$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)}"
base_image="asia-southeast1-docker.pkg.dev/maliev-website/maliev-website-artifact/maliev-payment-service"
kustomize_bin="${KUSTOMIZE_BIN:-kustomize}"

path_for_kustomize() {
  if [[ "$kustomize_bin" == *.exe ]] && command -v wslpath >/dev/null 2>&1; then
    wslpath -w "$1"
  else
    printf '%s\n' "$1"
  fi
}

case "$environment" in
  development) expected_image="asia-southeast1-docker.pkg.dev/maliev-website/maliev-payment-artifact-dev/maliev-payment-service" ;;
  staging) expected_image="asia-southeast1-docker.pkg.dev/maliev-website/maliev-payment-artifact-staging/maliev-payment-service" ;;
  production) expected_image="asia-southeast1-docker.pkg.dev/maliev-website/maliev-payment-artifact-prod/maliev-payment-service" ;;
  *)
    echo "Unsupported PaymentService environment: $environment" >&2
    usage
    exit 2
    ;;
esac

if [[ "$image" != "$expected_image" ]]; then
  echo "PaymentService $environment must use $expected_image" >&2
  exit 2
fi

if [[ ! "$digest" =~ ^sha256:[0-9a-f]{64}$ ]]; then
  echo "Digest must be an exact lowercase sha256 value." >&2
  exit 2
fi

command -v "$kustomize_bin" >/dev/null 2>&1 || [[ -x "$kustomize_bin" ]] || {
  echo "kustomize is required (set KUSTOMIZE_BIN when it is not on PATH)." >&2
  exit 2
}

overlay="$repo_root/3-apps/maliev-payment-service/overlays/$environment"
kustomization="$overlay/kustomization.yaml"
metadata_patch="$overlay/build-metadata-patch.yaml"

if [[ ! -f "$kustomization" ]]; then
  echo "PaymentService overlay not found: $overlay" >&2
  exit 2
fi

backup_dir="$(mktemp -d)"
cp "$kustomization" "$backup_dir/kustomization.yaml"
if [[ -f "$metadata_patch" ]]; then
  cp "$metadata_patch" "$backup_dir/build-metadata-patch.yaml"
fi

restore_on_error() {
  cp "$backup_dir/kustomization.yaml" "$kustomization"
  if [[ -f "$backup_dir/build-metadata-patch.yaml" ]]; then
    cp "$backup_dir/build-metadata-patch.yaml" "$metadata_patch"
  else
    rm -f "$metadata_patch"
  fi
}

cleanup() {
  rm -rf "$backup_dir"
}

trap restore_on_error ERR
trap cleanup EXIT

temporary_patch="$overlay/.build-metadata-patch.yaml.tmp"
printf '%s\n' \
  'apiVersion: apps/v1' \
  'kind: Deployment' \
  'metadata:' \
  '  name: maliev-payment-service' \
  'spec:' \
  '  template:' \
  '    spec:' \
  '      containers:' \
  '        - name: maliev-payment-service' \
  '          env:' \
  '            - name: BuildMetadata__ImageDigest' \
  "              value: \"$digest\"" > "$temporary_patch"
mv "$temporary_patch" "$metadata_patch"

(
  cd "$overlay"
  "$kustomize_bin" edit set image "$base_image=$image@$digest"
  if ! grep -Fq 'path: build-metadata-patch.yaml' kustomization.yaml; then
    "$kustomize_bin" edit add patch --path build-metadata-patch.yaml
  fi
)

"$kustomize_bin" build "$(path_for_kustomize "$overlay")" >/dev/null
trap - ERR

echo "Updated PaymentService $environment to $image@$digest"
