# Maliev GitOps: Setup and Operations Guide

This repository is the **single source of truth** for all application and infrastructure configurations deployed to the Maliev project's Kubernetes clusters. This guide provides a complete overview of the repository structure, the end-to-end development workflow, one-time setup instructions, and detailed operational guides.

**Table of Contents**

- [Maliev GitOps: Setup and Operations Guide](#maliev-gitops-setup-and-operations-guide)
  - [Core Concepts](#core-concepts)
  - [Repository Structure Overview](#repository-structure-overview)
  - [End-to-End Workflows](#end-to-end-workflows)
    - [Onboarding a New Application](#onboarding-a-new-application)
    - [Promoting a Release](#promoting-a-release)
    - [Rolling Back a Faulty Deployment](#rolling-back-a-faulty-deployment)
  - [Step-by-Step Guide: Onboarding a New Application](#step-by-step-guide-onboarding-a-new-application)
  - [Detailed Operational Guides](#detailed-operational-guides)
    - [Secret Management](#secret-management)
    - [Managing DNS Records](#managing-dns-records)
    - [Health Probe Tuning](#health-probe-tuning)
  - [One-Time Setup Guide](#one-time-setup-guide)
    - [A. Setting up the CI Pipeline (For each C# repo)](#a-setting-up-the-ci-pipeline-for-each-c-repo)
    - [B. Setting up the GitOps Controller (In Kubernetes)](#b-setting-up-the-gitops-controller-in-kubernetes)

---

## Core Concepts

* **GitOps**: The practice of using this Git repository as the declarative source of truth. Changes are made via Pull Request and an automated controller (Argo CD) in the cluster synchronizes the state.
* **App of Apps Pattern**: The scalable, industry-standard GitOps practice we use for managing a large number of applications. A single "root" Argo CD application manages other Argo CD applications, which in turn manage the actual services. This provides a centralized overview and simplifies adding new services.
* **Kustomize**: The tool used to manage configuration variants for different environments (`development`, `staging`, `production`) without duplicating YAML files. We use a `base`/`overlays` pattern.

---

## Repository Structure Overview

```
.
├── 1-cluster-infra/  # Core infrastructure components (e.g., NGINX, Cert-Manager)
├── 2-environments/   # Environment-specific configurations (e.g., namespaces, RBAC)
├── 3-apps/           # Application-specific manifests, one directory per app
│   └── maliev-auth-service/
│       ├── base/         # Environment-agnostic manifests (Deployment, Service)
│       └── overlays/     # Environment-specific patches
│           ├── development/
│           ├── staging/
│           └── production/
└── argocd/             # Argo CD application definitions (App of Apps)
    ├── projects/       # Argo CD AppProject definitions
    └── environments/   # Parent applications for each environment
        └── dev/
            └── apps/   # Argo CD Application manifest for each app in dev
```

---

## End-to-End Workflows

### Onboarding a New Application

As a DevOps Engineer, I want to follow a standard process to deploy a new application to the `development` environment so that it is managed via GitOps.

*   **GIVEN** I have created the necessary file structure in `3-apps/` and the ArgoCD Application manifest in `argocd/environments/dev/apps/`.
*   **WHEN** my Pull Request is merged to `main`.
*   **THEN** the new application appears in the ArgoCD UI and becomes `Healthy` and `Synced` within 5 minutes.

### Promoting a Release

As a DevOps Engineer, I want to promote a new version of an application to `staging` or `production` by updating a single image tag.

*   **GIVEN** a new container image (`my-app:v1.1.0`) is available.
*   **WHEN** I update the `newTag` in the Kustomize overlay for the target environment (e.g., `3-apps/my-app/overlays/staging/kustomization.yaml`).
*   **THEN** ArgoCD updates the application in the target namespace to use the new image within 5 minutes.

### Rolling Back a Faulty Deployment

As a DevOps Engineer, I want to quickly roll back a faulty deployment by reverting a commit in Git.

*   **GIVEN** a deployment is failing due to a bad commit (e.g., an invalid image tag).
*   **WHEN** I revert the faulty commit in the `main` branch.
*   **THEN** ArgoCD automatically re-syncs the application and restores it to the previous working version within 10 minutes.

---

## Step-by-Step Guide: Onboarding a New Application

This section provides a detailed, prescriptive guide for onboarding a new application.

**Step 1: Create Application Manifests (`3-apps`)**

1.  Create a new directory for your application under `3-apps/`, e.g., `3-apps/my-new-app`.
2.  Inside, create a `base` directory containing the core, environment-agnostic Kubernetes manifests:
    *   `deployment.yaml`: The main workload definition.
    *   `service.yaml`: The service resource to expose the application.
    *   `hpa.yaml`: The Horizontal Pod Autoscaler configuration.
    *   `service-secrets.yaml`: An `ExternalSecret` manifest. It MUST reference the `gcp-secret-manager` `ClusterSecretStore`.
    *   `kustomization.yaml`: This file MUST list all the above resources and include `../../_common`.
3.  Inside your application directory, create an `overlays` directory containing subdirectories for `development`, `staging`, and `production`.
4.  In each environment overlay (e.g., `overlays/development`), create a `kustomization.yaml`. This file MUST:
    *   Reference the base: `resources: - ../../base`
    *   Set the correct namespace, e.g., `namespace: maliev-dev`.
    *   Include an `images` block to specify the container image and tag for that specific environment.
    *   Include `patches` to override base configurations, such as resource limits and secret keys.

**Step 2: Register the Application in ArgoCD (`argocd`)**

1.  Navigate to the `argocd/environments/dev/apps/` directory.
2.  Create a new YAML file for your application, e.g., `my-new-app.yaml`.
3.  This file defines an ArgoCD `Application` resource. It must specify:
    *   `metadata.name`: e.g., `my-new-app-dev`
    *   `metadata.namespace`: `argocd`
    *   `spec.project`: `maliev-dev`
    *   `spec.source.path`: The path to your application's **development overlay**, e.g., `3-apps/my-new-app/overlays/development`.
    *   `spec.source.repoURL`: The URL of the GitOps repository.
    *   `spec.destination.namespace`: The target namespace, e.g., `maliev-dev`.

**Step 3: Submit for Review**

1.  Commit all the new files and push them to a feature branch.
2.  Create a Pull Request to merge the changes into the `main` branch.
3.  Once the PR is approved and merged, ArgoCD will automatically detect the new application definition and deploy it.

---

## Detailed Operational Guides

### Secret Management

This repository uses the **External Secrets Operator** to securely manage secrets.

*   **Storage**: All secrets are stored in **Google Secret Manager**.
*   **Syncing**: `ExternalSecret` resources in this repository tell the operator to fetch a secret from Google Secret Manager and create a corresponding native Kubernetes `Secret`.
*   **Configuration**:
    *   The `base/service-secrets.yaml` for each application defines the `ExternalSecret` resource.
    *   The environment-specific overlay (`overlays/<env>`) patches this resource to specify the exact `key` (version) of the secret to pull from Google Secret Manager for that environment. This allows `development` to use a different database password than `production` while using the same base manifest.

### Managing DNS Records

All of the following `A` records should be configured in your DNS provider to point to your main static IP address: **`100.200.300.255`**.

**Production Environment**

| Hostname / Name       | Type | Value / Points to |
|:--------------------- |:---- |:----------------- |
| `@` (or `maliev.com`) | A    | `100.200.300.255`  |
| `www`                 | A    | `100.200.300.255`  |
| `api`                 | A    | `100.200.300.255`  |

**Staging & Development Environments** are prefixed accordingly (e.g., `staging.api`, `dev.api`).

### Health Probe Tuning

The `deployment.yaml` for each service contains `livenessProbe` and `readinessProbe` sections. The key parameter to tune for each service is **`initialDelaySeconds`**. Set this to be slightly longer than your service's average startup time to prevent premature restarts.

---

## One-Time Setup Guide

This section covers the initial setup required to use this GitOps repository.

### A. Setting up the CI Pipeline (For each C# repo)

For each of your C# microservice repositories, you must configure a GitHub Actions workflow to automatically build and push container images.

1.  **Copy Workflow**: Copy `example-ci.yml` from this repo to your service repo at `.github/workflows/ci.yml`.
2.  **Edit Workflow**: Change the `SERVICE_NAME` environment variable in the file.
3.  **Create GitHub Secrets**: In your service repo's settings, create two secrets:
    *   `GCP_SA_KEY`: A Google Cloud Service Account key with the **"Artifact Registry Writer"** role.
    *   `GITOPS_PAT`: A GitHub Personal Access Token with the **`repo`** scope to allow the action to open Pull Requests in this repository.

### B. Setting up the GitOps Controller (In Kubernetes)

1.  **Install Argo CD**: Follow the official Argo CD documentation to install it in your cluster.
2.  **Apply the Root Application**: Apply the `root-app.yaml` from the `argocd` directory. This is the only manual `kubectl apply` needed. It bootstraps the entire App of Apps structure.
    ```bash
    kubectl apply -f maliev-gitops/argocd/root-app.yaml
    ```
