# Quickstart: Onboarding a New Application

This guide provides the minimal steps to get a new application deployed to the `development` environment.

### Prerequisites

-   Your application has been containerized and is available in an artifact registry.
-   You have cloned the `maliev-gitops` repository.

### Step 1: Create Application Manifests

1.  **Create Directories**:
    ```bash
    mkdir -p 3-apps/my-new-app/base
    mkdir -p 3-apps/my-new-app/overlays/development
    ```

2.  **Create Base Manifests**:
    -   Add `deployment.yaml`, `service.yaml`, and other core manifests to `3-apps/my-new-app/base/`.
    -   Create `3-apps/my-new-app/base/kustomization.yaml` to list these resources.

3.  **Create Development Overlay**:
    -   Create `3-apps/my-new-app/overlays/development/kustomization.yaml`.
    -   In this file, set the `namespace` to `maliev-dev` and specify the `newTag` for your container image.

### Step 2: Register with ArgoCD

1.  **Create ArgoCD Application Manifest**:
    -   Create a new file: `argocd/environments/dev/apps/my-new-app.yaml`.
    -   Define an `Application` resource pointing to your app's development overlay path: `3-apps/my-new-app/overlays/development`.

### Step 3: Deploy

1.  **Commit and Push**:
    ```bash
    git add .
    git commit -m "feat(my-new-app): onboard new application"
    git push
    ```
2.  **Create a Pull Request** to merge your changes into the `main` branch.
3.  **Verify**: Once merged, your application will be automatically deployed. Check its status in the ArgoCD UI.
