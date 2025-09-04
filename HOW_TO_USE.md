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

### Managing Cluster Issuers

Cert-Manager uses `ClusterIssuer` resources to represent certificate authorities. For better isolation and to avoid Let's Encrypt rate limits, we use different `ClusterIssuer` instances for production and non-production environments.

*   **`letsencrypt-prod`**: Used for production domains (e.g., `maliev.com`, `api.maliev.com`). It points to Let's Encrypt's production ACME server.
*   **`letsencrypt-staging`**: Used for development and staging domains (e.g., `dev.maliev.com`, `staging.maliev.com`). It points to Let's Encrypt's staging ACME server.

These `ClusterIssuer` definitions are located in `1-cluster-infra/02-cert-manager/release.yaml`. When adding a new domain or service, ensure its Ingress resource references the correct `ClusterIssuer` (`letsencrypt-prod` for production, `letsencrypt-staging` for dev/staging).

### Correcting Image Registry Paths

Initially, some services were configured to use `gcr.io/maliev-project` as their image registry. This has been corrected to use `asia-southeast1-docker.pkg.dev/maliev-website/maliev-website-artifact-<environment>`.

It is a best practice to use environment-specific repositories within your artifact registry to prevent accidental deployments and improve security.

*   **`maliev-website-artifact-dev`**: For development environment images.
*   **`maliev-website-artifact-staging`**: For staging environment images.
*   **`maliev-website-artifact-prod`**: For production environment images.

Ensure your CI/CD pipelines are configured to push images to the correct environment-specific repository.

### Renaming Service Resources

For consistency and brevity, the `.api` suffix has been removed from the names of services in their Kubernetes manifests. For example, `maliev-authservice-api` has been renamed to `maliev-authservice`.

This change affects:
*   `metadata.name` of Deployments, Services, and HPAs.
*   `spec.selector.matchLabels.app` and `spec.template.metadata.labels.app` in Deployments.
*   `spec.scaleTargetRef.name` in HPAs.
*   `backend.service.name` in Ingress rules.

Ensure that any new services or manual modifications adhere to this new naming convention.

---

## Prerequisites

Before you start, ensure you have:
1.  An approved GitOps controller (like Argo CD or Flux) installed and running in the Kubernetes cluster.
2.  The GitOps controller configured to watch the paths in this repository (e.g., `2-environments/1-development` and `2-environments/3-production`).
3.  CI pipelines for your microservice repositories configured to automatically create Pull Requests against this repo.

### CI/CD Service Account and PAT

To enable your CI/CD pipelines (e.g., GitHub Actions) to interact with your Google Cloud project and your GitOps repository, you need to configure two important secrets in each of your service repositories on GitHub:

*   **`GCP_SA_KEY`**: This secret contains a Google Cloud service account key with the **"Artifact Registry Writer"** role. It allows your CI/CD pipeline to push Docker images to your Google Artifact Registry. It is recommended to use a dedicated service account for this purpose. A good name would be `github-actions-artifact-writer`.

*   **`GITOPS_PAT`**: This is a GitHub Personal Access Token (PAT) that allows your CI/CD pipeline to create pull requests and push changes to your `maliev-gitops` repository.

    **Important Note for Organization Repositories:** For repositories belonging to an organization, it is a best practice to use a dedicated machine user (bot account) to create the PAT. This avoids tying the CI/CD process to a specific person's account. You can create a new GitHub account to be used as a bot, and then grant that bot account write access to the `maliev-gitops` repository.

    To create the PAT:
    1.  Log in to GitHub as the user who will create the PAT (ideally, the bot account).
    2.  Go to `Settings > Developer settings > Personal access tokens > Tokens (classic)`.
    3.  Click **"Generate new token"**.
    4.  Give the token a descriptive name (e.g., `maliev-gitops-updater`).
    5.  Select the **`repo`** scope.
    6.  Click **"Generate token"**.
    7.  Copy the generated token immediately and store it securely.

---

## Task 1: Deploying a New Version of an Existing Service

This is the most common workflow. The goal is to update the running application to a new container image version.

1.  **Automated PR Creation**: Your service's CI/CD pipeline should do this for you. After it successfully builds and pushes a new image (e.g., `gcr.io/maliev-project/maliev-authservice.api:v2.5.2`), it should automatically create a Pull Request here.

2.  **Review the Pull Request**: The PR will contain a very simple change. For example, to deploy `v2.5.2` of the auth service to production, the change will be in `2-environments/3-production/kustomization.yaml`:

    ```diff
    ...    
    images:
    - name: gcr.io/maliev-project/maliev-authservice.api
    -  newTag: "v2.5.1"
    +  newTag: "v2.5.2"
    - name: gcr.io/maliev-project/maliev-countryservice.api
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

2.  **Add Manifests**: Create the core Kubernetes manifests in the `3-apps/new-cool-service/base/` directory. This typically includes:
    *   `deployment.yaml`: Defines the application deployment (e.g., container image, replicas, probes).
    *   `service.yaml`: Defines the Kubernetes Service to expose your application.
    *   `hpa.yaml` (Optional): Defines a Horizontal Pod Autoscaler for automatic scaling.
    *   Any other necessary manifests for dependencies (e.g., `redis-deployment.yaml`, `redis-service.yaml` if your service uses Redis).

    Also, create empty overlay files (`development.yaml`, `staging.yaml`, `production.yaml`) in the `overlays` directory. These will be used for environment-specific configurations like resource limits or node selectors.
    

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
    - name: asia-southeast1-docker.pkg.dev/maliev-website/maliev-website-artifact-prod/new.cool.service
      newTag: "v1.0.0"
    ```

4.  **Commit and PR**: Commit these changes and open a PR. Once merged, the GitOps controller will deploy the new service for the first time.