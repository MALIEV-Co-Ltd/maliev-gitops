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

---

## Core Concepts

* **GitOps**: The practice of using this Git repository as the declarative source of truth. Changes are made via Pull Request and an automated controller in the cluster synchronizes the state. We recommend free, open-source, CNCF-graduated tools like **Argo CD** or **Flux CD** for this.
* **GitHub Actions**: The CI/CD tool used to build, test, and containerize the C# microservices. The workflow files reside in each service's own repository.
* **Kustomize**: The tool used to manage configuration variants for different environments without duplicating YAML files.

---

## The End-to-End Workflow: From Dev to Production

This workflow describes the path of a single code change from a developer's machine to a live customer.

1. **Local Development:** A developer writes a new feature or bug fix in a C# service and tests it locally.

2.  **Code Review & Merge:** The developer opens a Pull Request in the service's own repository (e.g., `Maliev.AuthService`). It is reviewed and merged into the `main` branch.

3. **Automated Deployment to `development` Environment:**
   
   * The GitHub Action in the service's repository triggers automatically.
   * It builds a new container image (e.g., `maliev.authservice.api:a1b2c3d`).
   * It then automatically opens a Pull Request in **this `maliev-gitops` repository** to update the `development` environment with this new image tag.
   * Your team merges this PR.
   * **Result:** The latest change is now running in the `dev` environment (`dev.api.maliev.com`), where developers can test its integration with the latest versions of all other services.

4. **Manual Promotion to `staging` Environment:**
   
   * After developers confirm the feature works as expected in `dev`, it is declared a "release candidate."
   * A developer **manually creates a new Pull Request** in this `maliev-gitops` repository.
   * This new PR changes the image tag for the service in the **`staging` environment's** `kustomization.yaml` file to the specific version tested in `dev` (e.g., `a1b2c3d`).
   * **Result:** The exact, known-good version is now in the `staging` environment (`staging.api.maliev.com`) for formal QA and User Acceptance Testing (UAT).

5. **Manual Promotion to `production` Environment:**
   
   * After the change passes all testing in `staging`, it is approved for release.
   * A developer **manually creates another Pull Request** in `maliev-gitops` to promote the exact same version (`a1b2c3d`) to the **`production` environment**.
   * **Result:** The change is now live for all customers on `api.maliev.com`.

---

## One-Time Setup Guide

### A. Setting up the CI Pipeline (For each C# repo)

For each of your C# microservice repositories, perform the following steps. For Python-based services, you will need to create a custom CI pipeline (e.g., `deploy.yml` in `.github/workflows`) that builds and pushes your Docker image, and then updates this GitOps repository. An example of such a pipeline for the `Maliev.LineChatbotService` has been provided.

1. **Copy the Workflow File**: Copy the `example-ci.yml` file from the root of this project into your service repository at the path `.github/workflows/ci.yml`.

2. **Edit the Workflow File**: Open the newly copied `ci.yml` and edit the `SERVICE_NAME` environment variable at the top.

3. **Create GitHub Secrets**: In your service repository's settings (`Settings > Secrets and variables > Actions`), create two new repository secrets:
   
   * **`GCP_SA_KEY`**: Allows GitHub Actions to push container images to your Google Artifact Registry. To create it, go to the Google Cloud Console, create a Service Account, grant it the **"Artifact Registry Writer"** role, and create and download a JSON key. Copy the entire JSON content into the value of this secret.
   
   * **`GITOPS_PAT`**: Allows the GitHub Action to create a Pull Request in the `maliev-gitops` repository. To create it, go to your personal GitHub account's **Developer Settings**, generate a new **Personal access token (classic)**, give it a descriptive name, and check the **`repo`** scope. Copy the generated token into the value of this secret.

     **Note for Organization Repositories:** For repositories belonging to an organization, it is a best practice to use a dedicated machine user (bot account) to create the PAT. This avoids tying the CI/CD process to a specific person's account. You can create a new GitHub account to be used as a bot, and then grant that bot account write access to the `maliev-gitops` repository.

### B. Setting up the GitOps Controller (In Kubernetes)

You need a GitOps controller in your cluster to watch this repository. Here is an example of how to do this with **Argo CD**.

**Important Note for Cloud Shell Users:** If you encounter `Kubernetes cluster unreachable` errors when running `helm` or `kubectl` commands in Google Cloud Shell, you likely need to configure your `kubectl` context. Run the following command, replacing the placeholders with your cluster details:

```bash
gcloud container clusters get-credentials <cluster-name> --zone <cluster-zone> --project <project-id>
```

1. **Install Argo CD**: Follow the official Argo CD documentation to install it in your cluster.

2. **Create an `Application` Manifest**: To tell Argo CD to manage your production environment, you would apply a manifest like this to your cluster. Save this as `argocd-app.yaml` and apply it with `kubectl apply -f argocd-app.yaml`.
   
   ```yaml
   apiVersion: argoproj.io/v1alpha1
   kind: Application
   metadata:
     name: maliev-production-environment
     namespace: argocd
   spec:
     project: default
     source:
       repoURL: 'https://github.com/MALIEV-Co-Ltd/maliev-gitops.git'
       targetRevision: main
       path: 2-environments/3-production
     destination:
       server: 'https://kubernetes.default.svc'
       namespace: maliev-production
     syncPolicy:
       automated:
         prune: false
         selfHeal: true
       syncOptions:
       - CreateNamespace=true
   ```

### C. Creating an Argo CD User (Recommended)

For security, you should not use the default `admin` account for daily work. Here is how to create a new user.

1. **Create the User Account**: Edit the `argocd-cm` ConfigMap to declare the new user.
   
   ```bash
   kubectl edit cm argocd-cm -n argocd
   ```
   
   Add the following line under the `data` section (or create the `data` section if it doesn't exist):
   
   ```yaml
   data:
     accounts.maliev-user: apiKey, login
   ```

2. **Set the Password**: The easiest way is with the Argo CD CLI. First, log in as admin, then update the new user's password.
   
   ```bash
   # Log in with the initial password
   argocd login localhost:8080
   
   # Set the new password (the CLI will handle hashing)
   argocd account update-password --account maliev-user --new-password YOUR_CHOSEN_STRONG_PASSWORD
   ```

3. **Grant Permissions**: Edit the `argocd-rbac-cm` ConfigMap to give your new user permissions.
   
   ```bash
   kubectl edit cm argocd-rbac-cm -n argocd
   ```
   
   Add the following `data` section, ensuring the indentation is correct:
   
   ```yaml
   data:
     policy.csv: |
       p, role:org-admin, applications, *, */*, allow
       g, maliev-user, role:org-admin
   ```

4. **Log In**: You can now log out and log back in with the username `maliev-user` and your new password.

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

* **`livenessProbe`**: If this fails, Kubernetes restarts the container. It answers the question, "Is the application alive or deadlocked?"
* **`readinessProbe`**: If this fails, Kubernetes stops sending traffic to the container. It answers, "Is the application ready to serve new requests?"

The key parameter to tune for each service is **`initialDelaySeconds`**. You should set this to be slightly longer than your service's average startup time to prevent premature failures.

### 3. Onboarding a New Service

1. **Create App Directory**: In `3-apps/`, create a new folder for your service with `base` and `overlays` subdirectories.
2. **Add Manifests**: Create the `deployment.yaml`, `service.yaml`, etc., in the `base` directory.
3. **Update Environment Kustomizations**: Edit the `kustomization.yaml` for each environment and add your new service to the `bases`, `patches`, and `images` sections.

### 4. Deploying Monitoring Stack (Prometheus & Grafana)

This repository includes a placeholder for a comprehensive monitoring solution using Prometheus and Grafana, typically deployed via the `kube-prometheus-stack` Helm chart.

* **Prometheus**: An open-source monitoring system that collects and stores metrics from your applications and infrastructure.
* **Grafana**: An open-source platform for data visualization and analytics, used to create dashboards and alerts from your metrics.

They are complementary tools and are almost always used together.

**How to Deploy:**

To deploy this monitoring stack to your cluster, run the following Helm commands from an environment with `helm` and `kubectl` configured to access your Kubernetes cluster (e.g., Google Cloud Shell):

1. **Add the Prometheus Community Helm repository:**
   
   ```bash
   helm repo add prometheus-community https://prometheus-community.github.io/helm-charts
   ```

2. **Update your Helm repositories to fetch the latest charts:**
   
   ```bash
   helm repo update
   ```

3. **Install the `kube-prometheus-stack` Helm chart:** This will deploy Prometheus, Grafana, Alertmanager, and other components into a new `monitoring` namespace.
   
   ```bash
   helm install prometheus prometheus-community/kube-prometheus-stack --namespace monitoring --create-namespace
   ```

**How to Verify and Access Grafana:**

1. **Verify Prometheus Pods are Running:**
   
   ```bash
   kubectl --namespace monitoring get pods -l "release=prometheus"
   ```

2. **Get Grafana Admin Password:**
   
   ```bash
   kubectl --namespace monitoring get secrets prometheus-grafana -o jsonpath="{.data.admin-password}" | base64 -d ; echo
   ```

3. **Access Grafana (Local Port-Forward):**
   Run these two commands in your Cloud Shell. Then, open a web browser and navigate to `http://localhost:3000`. If using Cloud Shell, use the "Web Preview" feature.
   
   ```bash
   export POD_NAME=$(kubectl --namespace monitoring get pod -l "app.kubernetes.io/name=grafana,app.kubernetes.io/instance=prometheus" -oname)
   kubectl --namespace monitoring port-forward $POD_NAME 3000
   ```
