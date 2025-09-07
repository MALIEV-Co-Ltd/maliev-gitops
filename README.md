# Maliev GitOps: Setup and Operations Guide

This repository is the **single source of truth** for all application and infrastructure configurations deployed to the Maliev project's Kubernetes clusters. This guide provides a complete overview of the repository structure, the end-to-end development workflow, one-time setup instructions, and detailed operational guides.

**Table of Contents**

- [Core Concepts](#core-concepts)
- [Repository Structure Overview](#repository-structure-overview)
- [The End-to-End Workflow: From Dev to Production](#the-end-to-end-workflow-from-dev-to-production)
- [One-Time Setup Guide](#one-time-setup-guide)
  - [A. Setting up the CI Pipeline (For each C# repo)](#a-setting-up-the-ci-pipeline-for-each-c-repo)
  - [B. Setting up the GitOps Controller (In Kubernetes)](#b-setting-up-the-gitops-controller-in-kubernetes)
  - [C. Creating an Argo CD User (Recommended)](#c-creating-an-argo-cd-user-recommended)
- [Detailed Operational Guides](#detailed-operational-guides)
  - [1. Managing DNS Records](#1-managing-dns-records)
  - [2. Health Probe (Liveness & Readiness) Tuning](#2-health-probe-liveness--readiness-tuning)
  - [3. Onboarding a New Service](#3-onboarding-a-new-service)
  - [4. Secret Management](#4-secret-management)

---

## Core Concepts

* **GitOps**: The practice of using this Git repository as the declarative source of truth. Changes are made via Pull Request and an automated controller in the cluster synchronizes the state. We recommend free, open-source, CNCF-graduated tools like **Argo CD** or **Flux CD** for this.
* **App of Apps Pattern**: The scalable, industry-standard GitOps practice for managing a large number of applications. Instead of manually creating a deployment manifest for each service in each environment, we use a single "root" Argo CD application that manages other Argo CD applications. This provides a centralized overview and simplifies the process of adding new services and promoting them between environments.
* **GitHub Actions**: The CI/CD tool used to build, test, and containerize the C# microservices. The workflow files reside in each service's own repository.
* **Kustomize**: The tool used to manage configuration variants for different environments without duplicating YAML files.

---

## The End-to-End Workflow: From Dev to Production

This workflow describes the path of a single code change from a developer's machine to a live customer, using a standard Git branching model.

1.  **Feature Development**: A developer creates a `feature` branch from the `develop` branch in a service's repository (e.g., `Maliev.AuthService`).

2.  **Code Review & Merge to `develop`**: The developer opens a Pull Request to merge their feature into the `develop` branch. Once merged, the CI pipeline triggers.

3.  **Automated Deployment to `development` Environment**: The CI pipeline for the `develop` branch builds a new container image and automatically opens a Pull Request in this `maliev-gitops` repository. This PR updates the image tag in the service's manifest (e.g., `argocd/environments/dev/apps/maliev-auth-service.yaml`). Once you merge this PR, the latest code is deployed to the `development` environment.

4.  **Preparing a Release for `staging`**: When you are ready to test a release, you create a `release/v1.1.0` branch from `develop` in the service's repository. You then open a PR in this `maliev-gitops` repo to change the `targetRevision` in the service's staging manifest (e.g., `argocd/environments/staging/apps/maliev-auth-service.yaml`) to point to this new `release/v1.1.0` branch. This deploys a stable release candidate to the `staging` environment for QA and UAT.

5.  **Promoting a Release to `production`**: After the release is approved in `staging`, you merge the `release/v1.1.0` branch into `main` and create a `v1.1.0` Git tag in the service's repository. You then open a final PR in `maliev-gitops` to update the `targetRevision` in the service's production manifest (e.g., `argocd/environments/prod/apps/maliev-auth-service.yaml`) to the new `v1.1.0` tag. This deploys the specific, tested version to your production customers.

---

## One-Time Setup Guide

### A. Setting up the CI Pipeline (For each C# repo)

For each of your C# microservice repositories, perform the following steps. For Python-based services, you will need to create a custom CI pipeline (e.g., `deploy.yml` in `.github/workflows`) that builds and pushes your Docker image, and then updates this GitOps repository. An example of such a pipeline for the `Maliev.LineChatbotService` has been provided.

1.  **Copy the Workflow File**: Copy the `example-ci.yml` file from the root of this project into your service repository at the path `.github/workflows/ci.yml`.

2.  **Edit the Workflow File**: Open the newly copied `ci.yml` and edit the `SERVICE_NAME` environment variable at the top.

3.  **Create GitHub Secrets**: In your service repository's settings (`Settings > Secrets and variables > Actions`), create two new repository secrets:
    
    *   **`GCP_SA_KEY`**: Allows GitHub Actions to push container images to your Google Artifact Registry. To create it, go to the Google Cloud Console, create a Service Account, grant it the **"Artifact Registry Writer"** role, and create and download a JSON key. Copy the entire JSON content into the value of this secret.
    
    *   **`GITOPS_PAT`**: Allows the GitHub Action to create a Pull Request in the `maliev-gitops` repository. To create it, go to your personal GitHub account's **Developer Settings**, generate a new **Personal access token (classic)**, give it a descriptive name, and check the **`repo`** scope. Copy the generated token into the value of this secret.
        **Note for Organization Repositories:** For repositories belonging to an organization, it is a best practice to use a dedicated machine user (bot account) to create the PAT. This avoids tying the CI/CD process to a specific person's account. You can create a new GitHub account to be used as a bot, and then grant that bot account write access to the `maliev-gitops` repository.

### B. Setting up the GitOps Controller (In Kubernetes)

You need a GitOps controller in your cluster to watch this repository. Here is how to do this with **Argo CD** using the **App of Apps** pattern.

**Important Note for Cloud Shell Users:** If you encounter `Kubernetes cluster unreachable` errors when running `helm` or `kubectl` commands in Google Cloud Shell, you likely need to configure your `kubectl` context. Run the following command, replacing the placeholders with your cluster details:

```bash
gcloud container clusters get-credentials <cluster-name> --zone <cluster-zone> --project <project-id>
```

1.  **Install Argo CD**: Follow the official Argo CD documentation to install it in your cluster.

2.  **Apply the Root Application**: The only manifest you need to apply manually is the `root-app.yaml` located in the `argocd` directory of this repository. This `Application` is the entry point for the App of Apps pattern. It will automatically deploy and manage all other applications for all environments.
    
    ```bash
    kubectl apply -f maliev-gitops/argocd/root-app.yaml
    ```
    
    Once applied, you can view the `root` application in the Argo CD UI. It will, in turn, show you the applications it manages for each of your environments.

### C. Creating an Argo CD User (Recommended)

For security, you should not use the default `admin` account for daily work. Here is how to create a new user.
**Note:** The `maliev` user has already been created.

1.  **Create the User Account**: Edit the `argocd-cm` ConfigMap to declare the new user.
    
    ```bash
    kubectl edit cm argocd-cm -n argocd
    ```
    
    Add the following line under the `data` section (or create the `data` section if it doesn't exist):
    
    ```yaml
    data:
      accounts.<new-user>: apiKey, login
    ```

2.  **Set the Password**: The easiest way is with the Argo CD CLI. First, log in as admin, then update the new user's password.
    
    ```bash
    # Log in with the initial password
    argocd login localhost:8080
    
    # Set the new password (the CLI will handle hashing)
    argocd account update-password --account <new-user> --new-password YOUR_CHOSEN_STRONG_PASSWORD
    ```

3.  **Grant Permissions**: Edit the `argocd-rbac-cm` ConfigMap to give your new user permissions.
    
    ```bash
    kubectl edit cm argocd-rbac-cm -n argocd
    ```
    
    Add the following `data` section, ensuring the indentation is correct:
    
    ```yaml
    data:
      policy.csv: |
        p, role:org-admin, applications, *, */*, allow
        g, <new-user>, role:org-admin
    ```

4.  **Log In**: You can now log out and log back in with the username `<new-user>` and your new password.

---

## Detailed Operational Guides

### 1. Managing DNS Records

All of the following `A` records should be configured in your DNS provider to point to your main static IP address: **`35.244.136.255`**.

**Production Environment**

| Hostname / Name       | Type | Value / Points to |
|:--------------------- |:---- |:----------------- |
| `@` (or `maliev.com`) | A    | `35.244.136.255`  |
| `www`                 | A    | `35.244.136.255`  |
| `api`                 | A    | `35.244.136.255`  |
| `intranet`            | A    | `35.244.136.255`  |
| `line-chatbot`        | A    | `35.244.136.255`  |

**Staging Environment**

| Hostname / Name    | Type | Value / Points to |
|:------------------ |:---- |:----------------- |
| `staging`          | A    | `35.244.136.255`  |
| `staging.www`      | A    | `35.244.136.255`  |
| `staging.api`      | A    | `35.244.136.255`  |
| `staging.intranet` | A    | `35.244.136.255`  |

**Development Environment**

| Hostname / Name | Type | Value / Points to |
|:--------------- |:---- |:----------------- |
| `dev`           | A    | `35.244.136.255`  |
| `dev.www`       | A    | `35.244.136.255`  |
| `dev.api`       | A    | `35.244.136.255`  |
| `dev.intranet`  | A    | `35.244.136.255`  |

### 2. Health Probe (Liveness & Readiness) Tuning

The `deployment.yaml` for each service contains `livenessProbe` and `readinessProbe` sections. These are critical for ensuring your application is stable.

*   **`livenessProbe`**: If this fails, Kubernetes restarts the container. It answers the question, "Is the application alive or deadlocked?"
*   **`readinessProbe`**: If this fails, Kubernetes stops sending traffic to the container. It answers, "Is the application ready to serve new requests?"

The key parameter to tune for each service is **`initialDelaySeconds`**. You should set this to be slightly longer than your service's average startup time to prevent premature failures.

### 3. Onboarding a New Service

1.  **Create App Directory**: In `3-apps/`, create a new folder for your service with the name `maliev-<app-name>`. This directory should contain `base` and `overlays` subdirectories.
2.  **Add Manifests**: Create the `deployment.yaml`, `service.yaml`, etc., in the `base` directory. Also create the overlay component directories and files (e.g., `overlays/development/kustomization.yaml`).
3.  **Create an Application Manifest**: In the `argocd/environments/<env>/apps` directory, create a new `Application` manifest for your service with the name `maliev-<app-name>.yaml`. This manifest will define how your service is deployed to each environment.
4.  **Automatic Deployment**: Argo CD will automatically detect the new application manifest in the `argocd/environments/<env>/apps` directory and deploy your new service.

### 4. Secret Management

This repository uses the External Secrets Operator to manage secrets securely across all environments. For detailed information about secret management, including naming conventions, templates, and troubleshooting, see:

-   **[HOW_TO_USE.md - Secret Management Section](HOW_TO_USE.md#understanding-secretsyaml-and-secret-management)** - Practical guide for day-to-day secret operations
-   **[secret-templates.yaml](secret-templates.yaml)** - Reusable templates for adding new service secrets

**Quick Reference:**

-   All secrets are stored in Google Secret Manager and synced to Kubernetes
-   Standardized naming: `maliev-{environment}-{scope}-{type}`
-   Templates available for common patterns (database, API, shared infrastructure)
-   Critical secrets already implemented: LINE Bot, JWT, database connections

For immediate help with GitHub Actions failures related to missing environment variables, see the analysis document.