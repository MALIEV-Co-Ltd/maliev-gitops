# Data Model

**Feature**: Onboarding and Managing Applications with the ArgoCD-based GitOps System

This feature describes a process rather than a data-intensive application. The key entities are conceptual and represent components of the GitOps workflow.

### Key Entities

-   **Git Repository**
    -   **Description**: The central repository holding all declarative configuration for infrastructure and applications. It is the single source of truth.
    -   **Attributes**:
        -   `URL`: `https://github.com/MALIEV-Co-Ltd/maliev-gitops.git`
        -   `Default Branch`: `main`
    -   **Relationships**: Contains the Kustomize overlays and ArgoCD Application manifests.

-   **Kustomize Overlay**
    -   **Description**: An environment-specific configuration layer (`development`, `staging`, `production`) that patches a common base configuration.
    -   **Attributes**:
        -   `path`: e.g., `3-apps/<app-name>/overlays/<env>`
        -   `namespace`: The target Kubernetes namespace for the environment.
        -   `image_tag`: The specific container image tag to be deployed.
    -   **Relationships**: References a `base` configuration. Is referenced by an `ArgoCD Application`.

-   **ArgoCD Application**
    -   **Description**: A custom resource that defines a deployed application, its source Git repository, path to its manifests (Kustomize overlay), and target cluster/namespace.
    -   **Attributes**:
        -   `name`: A unique name for the application in an environment (e.g., `my-app-dev`).
        -   `project`: The ArgoCD AppProject it belongs to (e.g., `maliev-dev`).
        -   `source.path`: The path to the Kustomize overlay in the Git repository.
        -   `destination.namespace`: The target namespace in the Kubernetes cluster.
    -   **Relationships**: Manages a set of Kubernetes resources defined in a Kustomize overlay.

-   **External Secret**
    -   **Description**: A resource that defines how to fetch secrets from an external store (Google Secret Manager).
    -   **Attributes**:
        -   `secretStoreRef`: The `ClusterSecretStore` to use (`gcp-secret-manager`).
        -   `extract.key`: The path to the secret in the external store. This is patched per environment.
        -   `target.name`: The name of the native Kubernetes `Secret` to create.
    -   **Relationships**: Associated with an application and an environment.
