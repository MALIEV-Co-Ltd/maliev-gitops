# Infrastructure Architecture

## Directory Organization

Infrastructure components like RabbitMQ and Redis are organized **per environment** rather than in the shared cluster-infra directory.

```
argocd/
├── cluster-infra/               # Shared infrastructure only (cert-manager, ingress-nginx, etc.)
│   ├── cert-manager-app.yaml
│   ├── ingress-nginx-app.yaml
│   └── ... (NO environment-specific apps here)
└── environments/                # Environment-specific applications
    ├── dev/
    │   ├── rabbitmq.yaml       ← RabbitMQ for development
    │   ├── redis.yaml          ← Redis for development
    │   ├── database.yaml
    │   └── ...
    ├── staging/
    │   ├── rabbitmq.yaml       ← RabbitMQ for staging
    │   ├── redis.yaml          ← Redis for staging
    │   ├── database.yaml
    │   └── ...
    └── prod/
        ├── rabbitmq.yaml       ← RabbitMQ for production
        ├── redis.yaml          ← Redis for production
        ├── database.yaml
        └── ...
```

## Rationale

### Why NOT in `argocd/cluster-infra/`?

**Cluster Infrastructure** should contain only resources that are:
- **Shared across all environments** (e.g., Cert Manager, Ingress Controller, External Secrets Operator)
- **Cluster-wide singletons** (e.g., CRDs, Cluster Roles, Admission Controllers)
- **Environment-agnostic** (same configuration regardless of dev/staging/prod)

### Why in `argocd/environments/{env}/`?

Stateful services like RabbitMQ and Redis are **environment-specific** because:
- Each environment has different resource requirements
- Each environment uses different credentials/secrets
- Each environment requires data isolation
- Each environment may have different replica counts and HA settings

## Application Names

Following the naming convention:

- **Development**: `maliev-dev-{service}` → Project: `maliev-dev`
- **Staging**: `maliev-staging-{service}` → Project: `maliev-staging`
- **Production**: `maliev-prod-{service}` → Project: `maliev-prod`

## Deployment Targets

Each ArgoCD application points to its respective Kustomize overlay:

- Dev: `1-cluster-infra/{service}/overlays/development` → `maliev-dev` namespace
- Staging: `1-cluster-infra/{service}/overlays/staging` → `maliev-staging` namespace
- Prod: `1-cluster-infra/{service}/overlays/production` → `maliev-prod` namespace

## Component Summary

| Component | Location | Reason |
|---|---|---|
| **Cert Manager** | `cluster-infra/` | Cluster-wide, shared by all environments |
| **Ingress NGINX** | `cluster-infra/` | Cluster-wide, routes to all environments |
| **External Secrets** | `cluster-infra/` | Cluster-wide operator, used by all environments |
| **ArgoCD** | `cluster-infra/` | Cluster-wide, manages all environments |
| **PostgreSQL** | `environments/{env}/database.yaml` | Per-environment, isolated data |
| **RabbitMQ** | `environments/{env}/rabbitmq.yaml` | Per-environment, isolated queues |
| **Redis** | `environments/{env}/redis.yaml` | Per-environment, isolated cache |
