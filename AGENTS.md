# AI Agent Guidelines for Maliev GitOps

This document provides context and rules for AI agents operating within the `maliev-gitops` repository.

## 1. Repository Context
This is a **GitOps repository** acting as the single source of truth for the Maliev infrastructure.
- **Platform:** Google Kubernetes Engine (GKE)
- **Deployment:** ArgoCD (App-of-Apps pattern)
- **Configuration:** Kustomize (Base/Overlay pattern)
- **Secrets:** External Secrets Operator (Google Secret Manager)

## 2. Build, Lint, & Test Commands

Since this is a configuration repository, "build" and "test" refer to validation and linting of YAML manifests.

### Linting
The primary validation tool is `kube-linter`.

**CRITICAL RULE:** Only lint **base** deployment files. **NEVER** lint overlay files (`overlays/*/kustomization.yaml` or patches), as they are intentionally incomplete fragments.

- **Run Linter (All Base Deployments):**
  ```bash
  ./scripts/lint-base-deployments.sh
  ```

- **Run Linter (Single File):**
  ```bash
  kube-linter lint 3-apps/myapp/base/deployment.yaml --config .kube-linter.yml
  ```

- **Auto-Fix Common Issues:**
  We have a Python script to automatically add missing security contexts, resources, and probes to base deployments.
  ```bash
  python3 fix_kube_linter.py
  ```

### Pre-Commit Hooks
Run all hooks locally before creating a PR:
```bash
pre-commit run --all-files
```

### "Build" (Validation)
To verify that overlays merge correctly without errors:
```bash
kustomize build 3-apps/myapp/overlays/development
```

## 3. Code Style & Conventions

### YAML Formatting
- **Indentation:** 2 spaces.
- **Lists:** `-` with one space after.
- **Keys:** camelCase (standard Kubernetes fields).

### Kustomize Structure
Strictly follow the Base/Overlay pattern:
- `base/`: Contains **COMPLETE** manifests (`deployment.yaml`, `service.yaml`). Must pass `kube-linter` in isolation.
- `overlays/{env}/`: Contains **PATCHES** only. Do not duplicate full manifests here.

### Deployment Manifest Standards (`base/deployment.yaml`)
All base deployments must include the following production-grade configurations:

#### 1. Security Context (Mandatory)
```yaml
securityContext:
  runAsNonRoot: true
  runAsUser: 1000
  runAsGroup: 3000
  readOnlyRootFilesystem: true  # Set to false only if absolutely necessary
  allowPrivilegeEscalation: false
  capabilities:
    drop:
      - ALL
```

#### 2. Resource Limits (Mandatory)
Define reasonable requests and limits.
```yaml
resources:
  requests:
    cpu: "10m"
    memory: "96Mi"
  limits:
    cpu: "25m"
    memory: "128Mi"
```

#### 3. Probes (Mandatory)
Tune `initialDelaySeconds` for the specific service.
```yaml
livenessProbe:
  httpGet:
    path: /health/live
    port: 8080
  initialDelaySeconds: 15
readinessProbe:
  httpGet:
    path: /health/ready
    port: 8080
  initialDelaySeconds: 10
```

#### 4. Secrets & Configuration
- **NEVER** commit secrets to this repo.
- Use `envFrom` to inject secrets from `ExternalSecret` resources.
```yaml
envFrom:
  - secretRef:
      name: maliev-shared-secrets
```

#### 5. Image Naming
Use the full artifact registry path.
- **Base:** Use `latest` or a stable tag.
- **Overlays:** Specific tags are injected by CI.
```yaml
image: asia-southeast1-docker.pkg.dev/maliev-website/maliev-website-artifact/maliev-auth-service:latest
```

## 4. Workflow Rules

1.  **No Direct Apply:** Never run `kubectl apply`. All changes must go through PR -> Merge -> ArgoCD Sync.
2.  **Naming Conventions:**
    - Directories/Files: kebab-case (e.g., `maliev-auth-service`).
    - Kubernetes Resources: kebab-case.
3.  **File Operations:**
    - When adding a new app, ensure both `base` and at least one `overlay` (e.g., `development`) are created.
    - Use `fix_kube_linter.py` after creating new manifests to ensure compliance.

## 5. Troubleshooting Common Errors

- **Error:** `kube-linter` fails on an overlay file.
  - **Fix:** You are linting the wrong file. Only lint `base/*.yaml`.

- **Error:** "Missing field: securityContext"
  - **Fix:** Run `python3 fix_kube_linter.py` or manually add the secure defaults listed above.

- **Error:** "Readiness probe failed"
  - **Fix:** Check `initialDelaySeconds`. Application might be slow to start. Increase the delay in `base/deployment.yaml`.

## 6. Architecture Overview
- **1-cluster-infra:** System-wide components (Ingress, Cert-Manager).
- **2-environments:** Namespace configurations.
- **3-apps:** Business logic applications.
- **argocd:** The "App of Apps" definitions that point to the above directories.
