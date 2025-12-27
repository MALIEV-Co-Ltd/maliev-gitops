# Kustomize Linting Strategy

## Why We Don't Lint Overlays

### The Problem

Kustomize uses a **base + overlay** pattern where:
- **Base files** contain complete Kubernetes manifests
- **Overlay files** contain patches (incomplete YAML fragments)

When kube-linter tries to validate overlay files, it fails because they're incomplete:

```yaml
# ❌ Overlay file - INCOMPLETE (kube-linter will fail)
# 3-apps/myapp/overlays/development/kustomization.yaml
patches:
  - target:
      kind: Deployment
      name: myapp
    patch: |-
      - op: replace
        path: /spec/replicas
        value: 1
```

This patch only changes the replica count. It has no:
- containers
- securityContext
- resources
- probes

Kube-linter doesn't understand this is a **patch** and reports 20+ violations for "missing" fields.

### The Solution

**Lint only base deployment files:**
```bash
find 3-apps -name "deployment.yaml" -path "*/base/*" | xargs kube-linter lint
```

This validates complete manifests that have:
- ✅ Security contexts
- ✅ Resource limits
- ✅ Probes
- ✅ All required fields

At build time, Kustomize merges base + overlays → complete manifest:
```bash
kustomize build 3-apps/myapp/overlays/development
# Results in complete manifest with base + overlay changes
```

---

## File Structure

```
3-apps/
└── myapp/
    ├── base/
    │   ├── deployment.yaml          ← ✅ LINT THIS (complete manifest)
    │   ├── service.yaml             ← ✅ LINT THIS (complete manifest)
    │   └── kustomization.yaml       ← ❌ Skip (just references)
    └── overlays/
        ├── development/
        │   └── kustomization.yaml   ← ❌ Skip (patches only)
        ├── staging/
        │   └── kustomization.yaml   ← ❌ Skip (patches only)
        └── production/
            └── kustomization.yaml   ← ❌ Skip (patches only)
```

---

## Pre-Commit Hooks

We use pre-commit hooks to catch issues before they reach CI:

### Installation

```bash
# Install pre-commit
pip install pre-commit

# Install hooks in this repo
cd maliev-gitops
pre-commit install
```

### What Gets Checked

1. **YAML linting** (yamllint) - Syntax and formatting
2. **Kube-linter** (base deployments only) - Kubernetes best practices
3. **Git hygiene** - Trailing whitespace, merge conflicts, large files

### Running Manually

```bash
# Run all hooks on staged files
pre-commit run

# Run all hooks on all files
pre-commit run --all-files

# Run only kube-linter
./scripts/lint-base-deployments.sh

# Skip hooks for emergency commits (NOT RECOMMENDED)
git commit --no-verify
```

---

## CI/CD Integration

Our GitHub Actions workflow uses the same strategy:

```yaml
# .github/workflows/validate.yml
- name: Check Kubernetes best practices (apps)
  run: |
    curl -L https://github.com/stackrox/kube-linter/releases/latest/download/kube-linter-linux.tar.gz | tar xz
    find 3-apps -name "deployment.yaml" -path "*/base/*" | xargs ./kube-linter lint --config .kube-linter.yml --format sarif > kube-linter-apps.sarif || true
```

This ensures:
- ✅ Same validation locally and in CI
- ✅ Only complete manifests are linted
- ✅ Overlays are skipped (they merge at runtime)

---

## Kustomize Overlay Patterns

### Strategic Merge Patch
```yaml
# overlays/development/replica-patch.yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: myapp
spec:
  replicas: 1  # Override just the replica count
```

### JSON Patch (RFC 6902)
```yaml
# kustomization.yaml
patches:
  - target:
      kind: Deployment
      name: myapp
    patch: |-
      - op: replace
        path: /spec/replicas
        value: 1
```

### Image Tag Patching (Our GitOps Pattern)
```yaml
# CI creates this overlay to update image tags
images:
  - name: asia-southeast1-docker.pkg.dev/maliev-website/maliev-website-artifact/myapp
    newTag: abc123def  # Specific commit SHA
```

All these patterns produce **incomplete YAML** that can't be linted independently.

---

## Troubleshooting

### Error: "kube-linter: command not found"

Install kube-linter:
```bash
# macOS
brew install kube-linter

# Linux
wget https://github.com/stackrox/kube-linter/releases/latest/download/kube-linter-linux.tar.gz
tar xzf kube-linter-linux.tar.gz
sudo mv kube-linter /usr/local/bin/

# Windows
choco install kube-linter
```

### Error: "found X lint errors" in CI

1. Check which files failed:
   ```bash
   gh run view <run-id> --log | grep "Error:"
   ```

2. Lint locally:
   ```bash
   ./scripts/lint-base-deployments.sh
   ```

3. Fix base deployment files in `3-apps/*/base/deployment.yaml`

4. DO NOT try to fix overlay files - they're supposed to be incomplete!

---

## Best Practices

1. ✅ **DO** add security contexts to base deployments
2. ✅ **DO** add resource limits to base deployments
3. ✅ **DO** add probes to base deployments
4. ✅ **DO** keep overlays minimal (only patch what's needed)
5. ❌ **DON'T** lint overlay files
6. ❌ **DON'T** duplicate base fields in overlays
7. ❌ **DON'T** commit without running pre-commit hooks

---

## References

- [Kustomize Documentation](https://kustomize.io/)
- [Kube-linter GitHub](https://github.com/stackrox/kube-linter)
- [Strategic Merge Patch](https://github.com/kubernetes/community/blob/master/contributors/devel/sig-api-machinery/strategic-merge-patch.md)
- [JSON Patch RFC 6902](https://tools.ietf.org/html/rfc6902)
