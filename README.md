# Maliev GitOps

[![Build Status](https://img.shields.io/badge/ArgoCD-Synced-success)](https://github.com/ORGANIZATION/maliev-gitops)
[![Kubernetes](https://img.shields.io/badge/Kubernetes-GKE-blue)](https://cloud.google.com/kubernetes-engine)
[![Environment](https://img.shields.io/badge/Environment-Multi--Environment-blue)](https://kustomize.io/)

The single source of truth for all application and infrastructure configurations for the Maliev platform.

**Role in MALIEV Architecture**: The central control plane for infrastructure delivery. It uses a declarative GitOps pattern (ArgoCD) to synchronize the state of Kubernetes clusters with the configurations defined in this repository, ensuring consistency, reliability, and automated promotion across Development, Staging, and Production environments.

---

## 🏗️ Architecture & Tech Stack

- **Pattern**: App-of-Apps (Scalable ArgoCD orchestration)
- **Controller**: ArgoCD (Real-time synchronization engine)
- **Configuration**: Kustomize (Base/Overlay pattern for environment parity)
- **Secret Management**: External Secrets Operator (Sync from Google Secret Manager)
- **Monitoring**: Integrated Health Probes & OpenTelemetry collectors
- **Infrastructure Provider**: Google Kubernetes Engine (GKE)

---

## ⚖️ Constitution Rules

This repository enforces the platform's infrastructure mandates:

### Declarative Source of Truth
- ❌ **No Manual Changes**: Direct `kubectl` modifications are strictly forbidden. All changes MUST be via Pull Request.
- ❌ **No Secrets in Repo**: Sensitive data MUST be stored in Google Secret Manager and synced via ExternalSecrets.

### Mandatory Practices
- ✅ **Kustomize Overlays**: Environment-specific patches MUST follow the `base/overlays` directory structure.
- ✅ **EnvFrom Injection**: Every deployment MUST use `envFrom` to reference standardized secret groups (e.g., `maliev-shared-secrets`).
- ✅ **Automated Probes**: Liveness and Readiness probes MUST be tuned for each service to ensure zero-downtime rolling updates.

---

## 📂 Repository Structure

```
.
├── 1-cluster-infra/  # Core infrastructure components (NGINX, Cert-Manager, OTel)
├── 2-environments/   # Environment-specific cluster config (Namespaces, RBAC)
├── 3-apps/           # Application manifests (Base + Dev/Staging/Prod overlays)
└── argocd/             # ArgoCD Application definitions (The "App of Apps" root)
```

---

## 🚀 Key Workflows

### 1. Onboarding a New Application
1. Create a service directory in `3-apps/` with `base` and `overlays`.
2. Define the ArgoCD application manifest in `argocd/environments/{env}/apps/`.
3. Submit a Pull Request. Once merged, ArgoCD will automatically provision the resource.

### 2. Promoting a Release
Update the `newTag` in the target environment's `kustomization.yaml` (e.g., `3-apps/auth-service/overlays/staging/kustomization.yaml`). Merging this change triggers an automated rollout to the cluster.

### 3. Rapid Rollback
If a deployment fails, simply revert the last commit in the `main` branch. ArgoCD will restore the previous known-good state within minutes.

---

## 🔒 Secret Management

This platform uses the **External Secrets Operator** for industrial-grade security:
- **Source**: Google Secret Manager (GCP).
- **Automation**: `ExternalSecret` resources in this repo define the mapping between GCP secrets and Kubernetes native secrets.
- **Injection**: Pods consume these via `envFrom`, making them available as standard environment variables to the .NET configuration system.

---

## 🌐 Network Configuration

### DNS Management
Configure `A` records in the DNS provider pointing to the cluster's static IP: **`YOUR_CLUSTER_STATIC_IP`**.

| Hostname | Target IP |
|:--- |:--- |
| `maliev.com` | `YOUR_CLUSTER_STATIC_IP` |
| `api.maliev.com` | `YOUR_CLUSTER_STATIC_IP` |
| `dev.api.maliev.com` | `YOUR_CLUSTER_STATIC_IP` |

---

## 🏥 Health & Monitoring

Standardized probes are defined in the `base/deployment.yaml` for every service:
- **Liveness**: Restarts a pod if it enters a deadlock state.
- **Readiness**: Controls when a pod is allowed to receive traffic.
- **Tuning**: Adjust `initialDelaySeconds` based on the specific service's cold-start bootstrap time.

---

## 📦 One-Time Setup

1. **Install ArgoCD**: Deploy the controller to the `argocd` namespace.
2. **Bootstrap Root**: Execute the one-time manual command to start the App-of-Apps engine:
```bash
kubectl apply -f maliev-gitops/argocd/root-app.yaml
```

---

## 📄 License

Proprietary - © 2025 MALIEV Co., Ltd. All rights reserved.
