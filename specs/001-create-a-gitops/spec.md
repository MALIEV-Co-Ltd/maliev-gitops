# Feature Specification: Onboarding and Managing Applications with the ArgoCD-based GitOps System

**Feature Branch**: `001-create-a-gitops`  
**Created**: 2025-10-08
**Status**: Detailed Draft  
**Input**: User description: "Create a GitOps system using ArgoCD for Kubernetes Engine."

## 1. Onboarding Process: Step-by-Step

This section provides a detailed, prescriptive guide for onboarding a new application.

**Step 1: Create Application Manifests (`3-apps`)**

1.  Create a new directory for your application under `3-apps/`, e.g., `3-apps/my-new-app`.
2.  Inside, create a `base` directory containing the core, environment-agnostic Kubernetes manifests:
    *   `deployment.yaml`: The main workload definition.
    *   `service.yaml`: The service resource to expose the application.
    *   `hpa.yaml`: The Horizontal Pod Autoscaler configuration.
    *   `service-secrets.yaml`: An `ExternalSecret` manifest for secret management. It MUST reference the `gcp-secret-manager` `ClusterSecretStore`.
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

## 2. User Scenarios & Testing

### User Story 1 - Onboarding a New Application

**As a DevOps Engineer**, I want to follow the documented onboarding process to deploy a new application to the `development` environment.

**Acceptance Scenarios**:

1.  **Given** I have created the file structure in `3-apps/my-new-app` as per the "Onboarding Process",
2.  **And** I have created the ArgoCD Application manifest in `argocd/environments/dev/apps/my-new-app.yaml`,
3.  **When** my Pull Request is merged to `main`,
4.  **Then** the `my-new-app-dev` application MUST appear in the ArgoCD UI within 5 minutes.
5.  **And** the application status MUST be `Healthy` and `Synced`.
6.  **And** all associated Kubernetes resources (Deployment, Service, Pods) MUST be present in the `maliev-dev` namespace.

### User Story 2 - Promoting an Application

**As a DevOps Engineer**, I want to promote a new version of an application by updating the image tag in the target environment's overlay.

**Acceptance Scenarios**:

1.  **Given** a new container image `my-new-app:v1.1.0` has been pushed to the artifact registry,
2.  **When** I update the `newTag` in `3-apps/my-new-app/overlays/staging/kustomization.yaml` to `v1.1.0`,
3.  **And** the change is merged to `main`,
4.  **Then** ArgoCD MUST trigger an update for the `my-new-app-staging` application.
5.  **And** the running pods in the `maliev-staging` namespace MUST be updated to the `v1.1.0` image within 5 minutes.

### User Story 3 - Automated Validation Workflow

**As a DevOps Engineer**, I want a CI pipeline for the GitOps repository that automatically validates any proposed changes, so that I can prevent errors and inconsistencies from being merged.

**Acceptance Scenarios**:

1.  **Given** a pull request is opened with changes to Kubernetes manifests,
2.  **When** the validation workflow runs,
3.  **Then** the workflow MUST execute a series of checks, including YAML linting, Kustomize build validation, and structural analysis.
4.  **Given** the validation workflow detects an error (e.g., an invalid Kustomize overlay or a `kind: Secret` resource),
5.  **When** the workflow completes,
6.  **Then** it MUST fail and report the error in the pull request, blocking the merge.

## 3. Requirements

### Functional Requirements

- **FR-001**: The system's state MUST be defined by the Kustomize and YAML files within the `https://github.com/MALIEV-Co-Ltd/maliev-gitops.git` repository.
- **FR-002**: New applications MUST be onboarded by creating a standard file structure under `3-apps/` and a corresponding ArgoCD `Application` manifest under `argocd/environments/<env>/apps/`.
- **FR-003**: Environment-specific configuration (e.g., image tags, resource limits, secret keys) MUST be managed via Kustomize overlays.
- **FR-004**: Application promotion MUST be performed by updating the `newTag` in an environment's `kustomization.yaml`.
- **FR-005**: Secrets MUST be managed via `ExternalSecret` resources which reference the `gcp-secret-manager` `ClusterSecretStore`. Each environment overlay MUST patch the `extract.key` field to point to the correct secret version in GCP Secret Manager.
- **FR-006**: Access to ArgoCD MUST be limited to `Admin` (full control) and `Developer` (read-only) roles.

### GitOps Validation Workflow

- **FR-007**: A GitHub Actions workflow MUST be triggered on every pull request targeting the `main` branch.
- **FR-008**: The workflow MUST perform static analysis on all YAML files to check for syntax errors and Kubernetes best practices.
- **FR-009**: The workflow MUST verify that all Kustomize overlays in `3-apps/*/overlays/*` can be successfully built using `kustomize build`.
- **FR-010**: The workflow MUST enforce the "No Secrets in Git" principle by failing if any resource with `kind: Secret` is detected.
- **FR-011**: The workflow MUST validate that all ArgoCD `Application` manifests point to valid, existing paths within the repository.
- **FR-012**: The workflow MUST validate that all repository structure and naming conventions are followed as defined in the validation tasks.

## 4. Success Criteria

- **SC-001**: A developer can successfully onboard a new application by following the "Onboarding Process" documentation without assistance.
- **SC-002**: The end-to-end time from a PR merge to a successful deployment in the `development` environment MUST be less than 5 minutes.
- **SC-003**: The process for promoting an application to `staging` or `production` MUST not require any changes outside of updating a single `newTag` value in the corresponding overlay.