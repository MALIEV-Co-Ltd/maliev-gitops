#!/usr/bin/env bash

set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
fixture_root="$(mktemp -d "$repo_root/.tmp-payment-promotion.XXXXXX")"
kustomize_bin="${KUSTOMIZE_BIN:-kustomize}"

path_for_kustomize() {
  if [[ "$kustomize_bin" == *.exe ]] && command -v wslpath >/dev/null 2>&1; then
    wslpath -w "$1"
  else
    printf '%s\n' "$1"
  fi
}
trap 'rm -rf "$fixture_root"' EXIT

mkdir -p "$fixture_root/3-apps"
cp -R "$repo_root/3-apps/maliev-payment-service" "$fixture_root/3-apps/"
cp -R "$repo_root/3-apps/_common" "$fixture_root/3-apps/"

digest="sha256:0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef"
mock_dir="$fixture_root/mock-bin"
mkdir -p "$mock_dir"

printf '%s\n' \
  '#!/usr/bin/env bash' \
  'set -euo pipefail' \
  'for argument in "$@"; do' \
  '  if [[ "$argument" == *@sha256:* ]]; then' \
  '    printf "%s\n" "${argument##*@}"' \
  '    exit 0' \
  '  fi' \
  'done' \
  'exit 1' > "$mock_dir/registry-success"

printf '%s\n' \
  '#!/usr/bin/env bash' \
  'exit 1' > "$mock_dir/registry-query-failure"

printf '%s\n' \
  '#!/usr/bin/env bash' \
  'exit 0' > "$mock_dir/registry-missing-digest"

chmod +x "$mock_dir/registry-success" "$mock_dir/registry-query-failure" "$mock_dir/registry-missing-digest"

for environment in development staging production; do
  case "$environment" in
    development) registry_suffix="dev" ;;
    staging) registry_suffix="staging" ;;
    production) registry_suffix="prod" ;;
  esac

  image="asia-southeast1-docker.pkg.dev/maliev-website/maliev-payment-artifact-${registry_suffix}/maliev-payment-service"
  overlay="$fixture_root/3-apps/maliev-payment-service/overlays/$environment"

  MALIEV_GITOPS_ROOT="$fixture_root" \
    PAYMENT_REGISTRY_INSPECTOR="$mock_dir/registry-success" \
    "$repo_root/scripts/update-paymentservice-image.sh" "$environment" "$image" "$digest"
  MALIEV_GITOPS_ROOT="$fixture_root" \
    PAYMENT_REGISTRY_INSPECTOR="$mock_dir/registry-success" \
    "$repo_root/scripts/update-paymentservice-image.sh" "$environment" "$image" "$digest" >/dev/null

  grep -Fq "newName: $image" "$overlay/kustomization.yaml"
  grep -Fq "digest: $digest" "$overlay/kustomization.yaml"
  if grep -Fq "newTag:" "$overlay/kustomization.yaml"; then
    echo "newTag must not remain in $environment after digest promotion" >&2
    exit 1
  fi
  grep -Fq "path: build-metadata-patch.yaml" "$overlay/kustomization.yaml"
  if [[ "$(grep -Fc 'path: build-metadata-patch.yaml' "$overlay/kustomization.yaml")" -ne 1 ]]; then
    echo "Build metadata patch was duplicated in $environment." >&2
    exit 1
  fi
  grep -Fq "value: \"$digest\"" "$overlay/build-metadata-patch.yaml"

  rendered="$fixture_root/$environment.yaml"
  "$kustomize_bin" build "$(path_for_kustomize "$overlay")" > "$rendered"
  grep -Fq "image: $image@$digest" "$rendered"

  digest_occurrences="$(grep -Fc "$digest" "$rendered")"
  if [[ "$digest_occurrences" -ne 2 ]]; then
    echo "Expected image and BuildMetadata digest parity in $environment; found $digest_occurrences occurrences" >&2
    exit 1
  fi
done

development_overlay="$fixture_root/3-apps/maliev-payment-service/overlays/development"
before_rejection="$(sha256sum "$development_overlay/kustomization.yaml")"

if MALIEV_GITOPS_ROOT="$fixture_root" \
  PAYMENT_REGISTRY_INSPECTOR="$mock_dir/registry-success" \
  "$repo_root/scripts/update-paymentservice-image.sh" development \
  "asia-southeast1-docker.pkg.dev/maliev-website/maliev-payment-artifact-prod/maliev-payment-service" \
  "$digest" >/dev/null 2>&1; then
  echo "Updater accepted a production repository for development." >&2
  exit 1
fi

if MALIEV_GITOPS_ROOT="$fixture_root" \
  PAYMENT_REGISTRY_INSPECTOR="$mock_dir/registry-success" \
  "$repo_root/scripts/update-paymentservice-image.sh" development \
  "asia-southeast1-docker.pkg.dev/maliev-website/maliev-payment-artifact-dev/maliev-payment-service" \
  "release-v1.2.3" >/dev/null 2>&1; then
  echo "Updater accepted a tag instead of an immutable digest." >&2
  exit 1
fi

for unavailable_inspector in registry-query-failure registry-missing-digest; do
  if MALIEV_GITOPS_ROOT="$fixture_root" \
    PAYMENT_REGISTRY_INSPECTOR="$mock_dir/$unavailable_inspector" \
    "$repo_root/scripts/update-paymentservice-image.sh" development \
    "asia-southeast1-docker.pkg.dev/maliev-website/maliev-payment-artifact-dev/maliev-payment-service" \
    "$digest" >/dev/null 2>&1; then
    echo "Updater accepted an unverified digest with $unavailable_inspector." >&2
    exit 1
  fi
done

after_rejection="$(sha256sum "$development_overlay/kustomization.yaml")"
if [[ "$before_rejection" != "$after_rejection" ]]; then
  echo "Rejected promotion mutated the development overlay." >&2
  exit 1
fi

echo "PaymentService immutable image promotion contract passed."
