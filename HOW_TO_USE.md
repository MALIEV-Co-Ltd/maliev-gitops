# How to Use the Maliev GitOps Repository

**Table of Contents**

- [Understanding the Infrastructure (`1-cluster-infra`)](#understanding-the-infrastructure-1-cluster-infra)
- [Understanding `secrets.yaml`](#understanding-secretsyaml)
- [Prerequisites](#prerequisites)
- [Task 1: Deploying a New Version of an Existing Service](#task-1-deploying-a-new-version-of-an-existing-service)
- [Task 2: Adding or Changing a Configuration Variable](#task-2-adding-or-changing-a-configuration-variable)
- [Task 3: Adding a Brand New Service](#task-3-adding-a-brand-new-service)

---

This guide provides practical, step-by-step instructions for common operational tasks. It has been updated to reflect the detailed configurations of all microservices and infrastructure components.

### Understanding the Infrastructure (`1-cluster-infra`)

This directory contains the YAML manifests for the core, shared services that your applications depend on. These are automatically deployed with each environment.

- **`02-cert-manager`**: Contains your specific `ClusterIssuer` for Let's Encrypt, which automatically provisions TLS certificates for your domains.
- **`03-external-secrets`**: Contains the setup for the External Secrets Operator, which securely syncs secrets from Google Secret Manager into the cluster.
- **`05-sql-server`**: Contains the `StatefulSet` that defines your SQL Server database deployment. This includes its persistent storage (`PersistentVolumeClaim`) and the `LoadBalancer` service to expose it to your applications at a static IP.

### Understanding `secrets.yaml`

The `secrets.yaml` files in each environment are now populated with all the connection strings and passwords discovered from your applications. They work by creating Kubernetes `Secret` objects that are then mounted into your application pods as environment variables.

Your responsibility is to ensure that secrets with the names specified in `remoteRef.key` (e.g., `prod-customer-db-conn`, `prod-log-db-conn`, `prod-mssql-sa-password`) exist in your Google Secret Manager project.

---

## Prerequisites

Before you start, ensure you have:
1.  An approved GitOps controller (like Argo CD or Flux) installed and running in the Kubernetes cluster.
2.  The GitOps controller configured to watch the paths in this repository (e.g., `2-environments/1-development` and `2-environments/3-production`).
3.  CI pipelines for your microservice repositories configured to automatically create Pull Requests against this repo.

---

## Task 1: Deploying a New Version of an Existing Service

This is the most common workflow. The goal is to update the running application to a new container image version.

1.  **Automated PR Creation**: Your service's CI/CD pipeline should do this for you. After it successfully builds and pushes a new image (e.g., `gcr.io/maliev-project/maliev.authservice.api:v2.5.2`), it should automatically create a Pull Request here.

2.  **Review the Pull Request**: The PR will contain a very simple change. For example, to deploy `v2.5.2` of the auth service to production, the change will be in `2-environments/3-production/kustomization.yaml`:

    ```diff
    ...    
    images:
    - name: gcr.io/maliev-project/maliev.authservice.api
    -  newTag: "v2.5.1"
    +  newTag: "v2.5.2"
    - name: gcr.io/maliev-project/maliev.countryservice.api
      newTag: "v1.3.0"
    ...
    ```

3.  **Approve and Merge**: Review the change to ensure the version is correct. Once you merge the PR into the `main` branch, the GitOps controller will detect the update.

4.  **Verify the Deployment**: The GitOps controller will now automatically start a rolling update of the service in the cluster. You can watch this happen using its UI (e.g., Argo CD) or via `kubectl`:

    ```bash
    # Watch the pods in the production namespace
    kubectl get pods -n maliev-production -w
    ```

---

## Task 2: Adding or Changing a Configuration Variable

Let's say you need to add a new setting, `Redis__ConnectionString`, to the `auth-service`.

### Step 1: Is it a Secret?

First, decide if the value is sensitive. 
- If **yes** (passwords, API keys, connection strings), it's a **Secret**.
- If **no** (public URLs, simple flags), it's a **ConfigMap** value.

### Step 2: If it's a Secret

1.  **Store the Secret**: Add the new secret value to your secure backend, **Google Secret Manager**. For example, create a secret named `prod-redis-connection-string`.

2.  **Update `secrets.yaml`**: Edit the `ExternalSecret` definition for the production environment in `2-environments/3-production/secrets.yaml`. Add a new entry to fetch the value you just created.

    ```yaml
    apiVersion: external-secrets.io/v1beta1
    kind: ExternalSecret
    metadata:
      name: prod-redis-secret
      namespace: maliev-production
    spec:
      secretStoreRef: { ... }
      target:
        name: redis-connection # This is the k8s Secret that will be created
      data:
      - secretKey: connection-string
        remoteRef:
          key: prod-redis-connection-string # The key in Google Secret Manager
    ```

3.  **Update `deployment.yaml`**: Edit the base deployment file in `3-apps/auth-service/base/deployment.yaml`. Add the new environment variable, pointing to the Kubernetes secret that will be created by the operator.

    ```yaml
          env:
          # ... other env vars
          - name: Redis__ConnectionString
            valueFrom:
              secretKeyRef:
                name: redis-connection # The k8s secret name from target.name
                key: connection-string # The key from secretKey
    ```

### Step 3: If it's a ConfigMap Value

1.  **Update `configmap.yaml`**: Edit `2-environments/3-production/configmap.yaml` and add your new key-value pair.

    ```yaml
    apiVersion: v1
    kind: ConfigMap
    metadata:
      name: environment-config
    data:
      Some__Other__Url: "http://..."
      New__Setting: "some-value"
    ```

2.  **Update `deployment.yaml`**: Edit `3-apps/auth-service/base/deployment.yaml` to mount the new value.

    ```yaml
          env:
          # ... other env vars
          - name: New__Setting
            valueFrom:
              configMapKeyRef:
                name: environment-config
                key: New__Setting
    ```

---

## Task 3: Adding a Brand New Service

Let's say you've created `new-cool-service`.

1.  **Create App Directory**: In `3-apps/`, create the folder `new-cool-service` with the standard `base` and `overlays` subdirectories.

2.  **Add Manifests**: Create the `deployment.yaml`, `service.yaml`, etc., in the `3-apps/new-cool-service/base/` directory. Also create the `development.yaml` and `production.yaml` patches in the `overlays` directory.

3.  **Update Environment Kustomizations**: This is the most important step. You must edit the `kustomization.yaml` for **each environment** where you want to deploy the service.

    For `2-environments/3-production/kustomization.yaml`, you would add the new service in three places:

    ```yaml
    bases:
    # ... existing bases
    - ../../3-apps/new-cool-service/base

    patchesStrategicMerge:
    # ... existing patches
    - ../../3-apps/new-cool-service/overlays/production.yaml

    images:
    # ... existing images
    - name: gcr.io/maliev-project/new.cool.service
      newTag: "v1.0.0"
    ```

4.  **Commit and PR**: Commit these changes and open a PR. Once merged, the GitOps controller will deploy the new service for the first time.