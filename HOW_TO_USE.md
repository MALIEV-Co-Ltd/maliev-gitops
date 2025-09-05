# How to Use the Maliev GitOps Repository

**Table of Contents**

- [Understanding the Infrastructure (`1-cluster-infra`)](#understanding-the-infrastructure-1-cluster-infra)
- [Understanding `secrets.yaml` and Secret Management](#understanding-secretsyaml-and-secret-management)
- [Setting up Deploy Keys for Microservice Repositories](#setting-up-deploy-keys-for-microservice-repositories)
- [Managing Cluster Issuers](#managing-cluster-issuers)
- [Correcting Image Registry Paths](#correcting-image-registry-paths)
- [Renaming Service Resources](#renaming-service-resources)
- [Prerequisites](#prerequisites)
- [Task 1: Deploying a New Version of an Existing Service](#task-1-deploying-a-new-version-of-an-existing-service)
- [Task 2: Adding or Changing a Configuration Variable](#task-2-adding-or-changing-a-configuration-variable)
- [Task 3: Adding a Brand New Service](#task-3-adding-a-brand-new-service)

---

This guide provides practical, step-by-step instructions for common operational tasks. It has been updated to reflect the detailed configurations of all microservices and infrastructure components.

### Understanding the App of Apps Structure

This repository now uses the **App of Apps** pattern to manage applications in Argo CD. This is a more scalable and manageable approach for a large number of microservices.

Here's how it works:

1.  **`argocd/` directory**: This new directory at the root of the repository contains all the Argo CD `Application` manifests.
2.  **`root-app.yaml`**: This is the single, top-level application that you apply to your cluster. It is configured to find and deploy all other `Application` manifests within the `argocd/` directory.
3.  **Application Manifests**: For each service (like `line-chatbot-service`), there is a corresponding `Application` manifest in the `argocd/` directory (e.g., `line-chatbot-service.yaml`). This manifest defines how the service is deployed across all environments (development, staging, production).

This structure means that to add, remove, or modify a service's deployment, you will be editing the `Application` manifests in the `argocd/` directory, rather than the `kustomization.yaml` files in the `2-environments/` directories.

### Understanding the Infrastructure (`1-cluster-infra`)

This directory contains the YAML manifests for the core, shared services that your applications depend on. These are automatically deployed with each environment.

- **`02-cert-manager`**: Contains your specific `ClusterIssuer` for Let's Encrypt, which automatically provisions TLS certificates for your domains.
- **`03-external-secrets`**: Contains the setup for the External Secrets Operator, which securely syncs secrets from Google Secret Manager into the cluster.
- **`05-sql-server`**: Contains the `StatefulSet` that defines your SQL Server database deployment. This includes its persistent storage (`PersistentVolumeClaim`) and the `LoadBalancer` service to expose it to your applications at a static IP.

### Understanding `secrets.yaml` and Secret Management

The `secrets.yaml` files in each environment use the External Secrets Operator to securely sync secrets from Google Secret Manager into Kubernetes `Secret` objects, which are then mounted into your application pods as environment variables.

#### Current Secret Management Architecture

**✅ Implemented Secrets:**
- **LINE Bot Configuration**: `line-chatbot-secrets` (contains LINE_CHANNEL_SECRET, GEMINI_API_KEY, etc.)
- **JWT Secrets**: `jwt-secret` for authentication services
- **Database Connections**: `log-db-conn` (shared), `auth-service-db-conn`, `country-db-conn`

**📋 Secret Naming Standards:**
We follow a standardized naming convention for consistency across all environments:

**Format**: `{environment}-{scope}-{type}`
- **Environment**: `dev`, `staging`, `prod`
- **Scope**: `shared` (multiple services) or `{service-name}` (specific service)  
- **Type**: `db-conn`, `jwt`, `api`, `config`, `cert`

**Google Secret Manager Key Format**: `maliev-{environment}-{scope}-{type}`

**Examples:**
- `maliev-dev-shared-jwt` → Creates `jwt-secret` in dev environment
- `maliev-prod-auth-service-customer-db-conn` → Creates connection for auth service
- `maliev-staging-shared-log-db-conn` → Creates shared log database connection

#### Secret Content Structure

**Database Connection Secrets:**
```yaml
# Single connection string
connection-string: "Server=...;Database=...;User Id=...;Password=...;"

# Multiple connection strings (e.g., auth-service)
customer: "Server=...;Database=customer;..."
employee: "Server=...;Database=employee;..."
```

**JWT Secrets:**
```yaml
key: "your-jwt-signing-key"
issuer: "maliev.com"
audience: "maliev-services"
expiry-hours: "24"
```

**LINE Bot Configuration:**
```yaml
LINE_CHANNEL_SECRET: "..."
LINE_CHANNEL_ACCESS_TOKEN: "..."
GEMINI_API_KEY: "..."
GEMINI_MODEL: "gemini-2.5-flash"
GOOGLE_APPLICATION_CREDENTIALS_BASE64: "..."
REDIS_HOST: "redis-service"
```

#### Adding New Service Secrets

To add secrets for a new service, follow these templates (found in `secret-templates.yaml`):

**1. Single Database Service:**
```yaml
apiVersion: external-secrets.io/v1beta1
kind: ExternalSecret
metadata:
  name: {environment}-{service-name}-db
  namespace: maliev-{environment}
spec:
  secretStoreRef:
    name: gcp-secret-store
    kind: ClusterSecretStore
  target:
    name: {service-name}-db-conn
  data:
  - secretKey: connection-string
    remoteRef:
      key: maliev-{environment}-{service-name}-db-conn
```

**2. API Configuration Service:**
```yaml
apiVersion: external-secrets.io/v1beta1
kind: ExternalSecret
metadata:
  name: {environment}-{service-name}-api
  namespace: maliev-{environment}
spec:
  secretStoreRef:
    name: gcp-secret-store
    kind: ClusterSecretStore
  target:
    name: {service-name}-api-secrets
  dataFrom:
  - extract:
      key: maliev-{environment}-{service-name}-api-config
```

**Steps to Add a New Secret:**
1. Choose the appropriate template from `secret-templates.yaml`
2. Replace all `{placeholders}` with actual values
3. Create the corresponding secret in Google Secret Manager
4. Add the configured ExternalSecret to the environment `secrets.yaml` file
5. Commit and let ArgoCD sync the changes

Your responsibility is to ensure that secrets with the names specified in `remoteRef.key` exist in your Google Secret Manager project.

---

### Understanding `secrets.yaml` and Secret Management

The `secrets.yaml` files in each environment use the External Secrets Operator to securely sync secrets from Google Secret Manager into Kubernetes `Secret` objects, which are then mounted into your application pods as environment variables.

#### Current Secret Management Architecture

**✅ Implemented Secrets:**
- **LINE Bot Configuration**: `line-chatbot-secrets` (contains LINE_CHANNEL_SECRET, GEMINI_API_KEY, etc.)
- **JWT Secrets**: `jwt-secret` for authentication services
- **Database Connections**: `log-db-conn` (shared), `auth-service-db-conn`, `country-db-conn`

**📋 Secret Naming Standards:**
We follow a standardized naming convention for consistency across all environments:

**Format**: `{environment}-{scope}-{type}`
- **Environment**: `dev`, `staging`, `prod`
- **Scope**: `shared` (multiple services) or `{service-name}` (specific service)  
- **Type**: `db-conn`, `jwt`, `api`, `config`, `cert`

**Google Secret Manager Key Format**: `maliev-{environment}-{scope}-{type}`

**Examples:**
- `maliev-dev-shared-jwt` → Creates `jwt-secret` in dev environment
- `maliev-prod-auth-service-customer-db-conn` → Creates connection for auth service
- `maliev-staging-shared-log-db-conn` → Creates shared log database connection

#### Secret Content Structure

**Database Connection Secrets:**
```yaml
# Single connection string
connection-string: "Server=...;Database=...;User Id=...;Password=...;"

# Multiple connection strings (e.g., auth-service)
customer: "Server=...;Database=customer;..."
employee: "Server=...;Database=employee;..."
```

**JWT Secrets:**
```yaml
key: "your-jwt-signing-key"
issuer: "maliev.com"
audience: "maliev-services"
expiry-hours: "24"
```

**LINE Bot Configuration:**
```yaml
LINE_CHANNEL_SECRET: "..."
LINE_CHANNEL_ACCESS_TOKEN: "..."
GEMINI_API_KEY: "..."
GEMINI_MODEL: "gemini-2.5-flash"
GOOGLE_APPLICATION_CREDENTIALS_BASE64: "..."
REDIS_HOST: "redis-service"
```

#### Adding New Service Secrets

To add secrets for a new service, follow these templates (found in `secret-templates.yaml`):

**1. Single Database Service:**
```yaml
apiVersion: external-secrets.io/v1beta1
kind: ExternalSecret
metadata:
  name: {environment}-{service-name}-db
  namespace: maliev-{environment}
spec:
  secretStoreRef:
    name: gcp-secret-store
    kind: ClusterSecretStore
  target:
    name: {service-name}-db-conn
  data:
  - secretKey: connection-string
    remoteRef:
      key: maliev-{environment}-{service-name}-db-conn
```

**2. API Configuration Service:**
```yaml
apiVersion: external-secrets.io/v1beta1
kind: ExternalSecret
metadata:
  name: {environment}-{service-name}-api
  namespace: maliev-{environment}
spec:
  secretStoreRef:
    name: gcp-secret-store
    kind: ClusterSecretStore
  target:
    name: {service-name}-api-secrets
  dataFrom:
  - extract:
      key: maliev-{environment}-{service-name}-api-config
```

**Steps to Add a New Secret:**
1. Choose the appropriate template from `secret-templates.yaml`
2. Replace all `{placeholders}` with actual values
3. Create the corresponding secret in Google Secret Manager
4. Add the configured ExternalSecret to the environment `secrets.yaml` file
5. Commit and let ArgoCD sync the changes

Your responsibility is to ensure that secrets with the names specified in `remoteRef.key` exist in your Google Secret Manager project.

---

## Setting up Deploy Keys for Microservice Repositories

To allow Argo CD to access your individual microservice repositories (e.g., `Maliev.LineChatbotService`), you will use SSH Deploy Keys. A Deploy Key is an SSH key that grants access to a **single GitHub repository**.

**Important Considerations:**
*   **Repository-Specific:** Each microservice repository will need its own unique Deploy Key.
*   **Read-Only Access:** For GitOps, Argo CD typically only needs read access to your code repositories. Granting read-only access is more secure.
*   **No Passphrase for Automation:** Do NOT set a passphrase for Deploy Keys used by automated systems like Argo CD, as it cannot provide the passphrase.

### Step 1: Generate a new SSH key pair for the Deploy Key

Generate a new SSH key pair specifically for this Deploy Key. Do not reuse your personal SSH key. Replace `your_repo_name` with the actual repository name (e.g., `Maliev.LineChatbotService`).

```bash
ssh-keygen -t rsa -b 4096 -C "your_repo_name-deploy-key" -f ~/.ssh/id_rsa_your_repo_name_deploy_key
```

*   When prompted for a passphrase, **press Enter twice** to leave it empty.

This command will create two files in your `~/.ssh/` directory:
*   `id_rsa_your_repo_name_deploy_key` (your **private key**)
*   `id_rsa_your_repo_name_deploy_key.pub` (your **public key**)

### Step 2: Add the Public Key to your GitHub Repository

1.  **Copy your public key to your clipboard.**
    *   **On Windows (Git Bash):**
        ```bash
        cat ~/.ssh/id_rsa_your_repo_name_deploy_key.pub | clip
        ```
    *   **On macOS:**
        ```bash
        pbcopy < ~/.ssh/id_rsa_your_repo_name_deploy_key.pub
        ```
    *   **On Linux:**
        ```bash
        xclip -sel clip < ~/.ssh/id_rsa_your_repo_name_deploy_key.pub
        ```
    Alternatively, open the `.pub` file in a text editor and copy its entire content.

2.  **Go to your GitHub repository:**
    *   Navigate to the specific repository (e.g., `MALIEV-Co-Ltd/Maliev.LineChatbotService`).
    *   Click on **Settings**.
    *   In the left sidebar, click **Deploy keys**.
    *   Click the **Add deploy key** button.

3.  **Configure the Deploy Key:**
    *   Give your key a descriptive **Title** (e.g., "Argo CD for Maliev.LineChatbotService").
    *   Paste your copied public key into the **Key** field.
    *   **Ensure "Allow write access" is NOT checked.** This provides read-only access, which is more secure for Argo CD.
    *   Click **Add key**.

### Step 3: Add the Private Key to Argo CD Repository Settings

1.  **Copy the entire content of your private key file.**
    When running this command, the entire private key content will be copied into the clipboard.
    *   **On Windows (Git Bash):**
        ```bash
        cat ~/.ssh/id_rsa_your_repo_name_deploy_key | clip
        ```
    *   **On macOS:**
        ```bash
        pbcopy < ~/.ssh/id_rsa_your_repo_name_deploy_key
        ```
    *   **On Linux:**
        ```bash
        xclip -sel clip < ~/.ssh/id_rsa_your_repo_name_deploy_key
        ```

2.  **Add the private key to Argo CD:**
    *   Log in to your Argo CD UI.
    *   Go to **Settings > Repositories**.
    *   Click **CONNECT REPO**.
    *   Choose **Git**.
    *   For **Repository URL**, enter the SSH URL of your microservice repository (e.g., `git@github.com:MALIEV-Co-Ltd/Maliev.LineChatbotService.git`).
    *   For **SSH Private Key**, paste the entire content of your private key file.
    *   Click **CONNECT**.

Repeat these steps for each microservice repository that Argo CD needs to access.

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
2.  The GitOps controller configured to watch this repository by applying the `root-app.yaml` manifest from the `argocd` directory. This is the only manual `apply` step required.
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

This workflow describes how to promote a release through your environments using the new branching strategy.

### Step 1: Continuous Deployment to Development

Your CI/CD pipeline for each microservice should be configured to:
1.  Trigger on every merge to the **`develop`** branch.
2.  Build a new container image.
3.  Automatically create a Pull Request in this `maliev-gitops` repository that updates the `image` tag in the service's **`-dev.yaml`** application manifest (e.g., `argocd/auth-service-dev.yaml`).

Once you merge that PR, the `development` environment will be updated with the latest code from the `develop` branch.

### Step 2: Promoting a Release to Staging

1.  **Create a Release Branch**: In your microservice's repository, create a `release` branch from `develop` (e.g., `release/v1.1.0`).
2.  **Update the Staging Application**: In this `maliev-gitops` repository, create a Pull Request that changes the `targetRevision` in the service's **`-staging.yaml`** application manifest to point to your new release branch.

    ```diff
    # In argocd/your-service-staging.yaml
    spec:
      source:
    -   targetRevision: develop
    +   targetRevision: release/v1.1.0
    ```
3.  **Merge and Verify**: Merge the PR. Argo CD will now deploy the stable release candidate to your `staging` environment for final testing.

### Step 3: Releasing to Production

1.  **Merge and Tag**: Once staging is approved, in your microservice's repository, merge the `release` branch into `main` and create a Git tag (e.g., `v1.1.0`).
2.  **Update the Production Application**: In this `maliev-gitops` repository, create a Pull Request that changes the `targetRevision` in the service's **`-prod.yaml`** application manifest to point to the new version tag.

    ```diff
    # In argocd/your-service-prod.yaml
    spec:
      source:
    -   targetRevision: v1.0.0
    +   targetRevision: v1.1.0
    ```
3.  **Merge and Celebrate**: Merge the PR. Argo CD will deploy the new version to production. Remember to also merge your release branch back into `develop`.

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
      namespace: maliev-prod
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

    Also, create the overlay component directories and files (e.g., `overlays/development/kustomization.yaml` and `overlays/development/patch.yaml`).

3.  **Create an Application Manifest**: In the `argocd` directory, create a new `Application` manifest for your service, for example `argocd/new-cool-service.yaml`. This manifest will define how your service is deployed to each environment. You can use one of the existing service application manifests as a template.

4.  **Update the Root Kustomization**: Add a reference to your new application manifest in the `argocd/kustomization.yaml` file.

    ```yaml
    resources:
    # ... existing resources
    - new-cool-service.yaml
    ```

5.  **Commit and PR**: Commit these changes and open a PR. Once merged, the GitOps controller will deploy the new service for the first time.