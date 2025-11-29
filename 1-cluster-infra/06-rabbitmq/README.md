# RabbitMQ Environment-Specific Deployments

## Architecture Decision

RabbitMQ is deployed **per environment** (development, staging, production) to provide:

- **Isolation**: Changes in development don't affect production
- **Security**: Each environment has separate credentials  
- **Testing**: Safe testing of message queue configurations
- **Scalability**: Independent scaling per environment
- **Cost Optimization**: Dev uses smaller resources than production

## Directory Structure

```
06-rabbitmq/
├── base/                           # Base configuration (shared)
│   ├── rabbitmq-cluster.yaml      # RabbitMQ cluster definition
│   ├── service-alias.yaml         # Service alias for backward compatibility
│   ├── shared-secrets.yaml        # ExternalSecret template (patched per env)
│   └── kustomization.yaml         # Base kustomization
└── overlays/
    ├── development/               # Dev-specific settings
    │   └── kustomization.yaml     # 1 replica, reduced resources
    ├── staging/                   # Staging-specific settings
    │   └── kustomization.yaml     # 2 replicas, moderate resources
    └── production/                # Production-specific settings
        └── kustomization.yaml     # 3 replicas, full HA setup
```

## Configuration per Environment

### Development (`maliev-dev` namespace)
- **Replicas**: 1 (single instance)
- **Memory**: 256Mi request, 1Gi limit
- **Storage**: 2Gi
- **Secret**: `maliev-dev-shared-config`
- **Cluster Name**: `maliev-dev-rabbitmq`

### Staging (`maliev-staging` namespace)
- **Replicas**: 2 (basic HA)
- **Memory**: 512Mi request, 2Gi limit
- **Storage**: 5Gi
- **Secret**: `maliev-staging-shared-config`
- **Cluster Name**: `maliev-staging-rabbitmq`

### Production (`maliev-prod` namespace)
- **Replicas**: 3 (full HA)
- **Memory**: 1Gi request, 4Gi limit
- **Storage**: 10Gi
- **Secret**: `maliev-prod-shared-config`
- **Cluster Name**: `maliev-prod-rabbitmq`

## Secrets Configuration

Each environment requires a secret in Google Cloud Secret Manager:

### Secret Names
- Development: `maliev-dev-shared-config`
- Staging: `maliev-staging-shared-config`
- Production: `maliev-prod-shared-config`

### Required Keys
Each secret must contain:
- `RabbitMq__Username` - RabbitMQ admin username
- `RabbitMq__Password` - RabbitMQ admin password

### Example Secret Value (JSON)
```json
{
  "RabbitMq__Username": "malievadmin",
  "RabbitMq__Password": "your-secure-password-here",
  "Redis__ConnectionString": "redis-host:6379",
  "Other__Keys": "as-needed"
}
```

## Service Access

Applications connect to RabbitMQ using:

### Development Environment
```
Host: rabbitmq.maliev-dev.svc.cluster.local
Port: 5672 (AMQP)
Management UI: 15672
```

### Staging Environment
```
Host: rabbitmq.maliev-staging.svc.cluster.local
Port: 5672 (AMQP)
Management UI: 15672
```

### Production Environment
```
Host: rabbitmq.maliev-prod.svc.cluster.local
Port: 5672 (AMQP)
Management UI: 15672
```

## ArgoCD Applications

Each environment has its own ArgoCD application:

- `argocd/cluster-infra/rabbitmq-app.yaml` → Development
- `argocd/cluster-infra/rabbitmq-staging-app.yaml` → Staging
- `argocd/cluster-infra/rabbitmq-prod-app.yaml` → Production

## Migration from Shared Infrastructure

**Previous**: RabbitMQ was in `maliev-infra` namespace (shared)
**Current**: Environment-specific deployments in `maliev-dev`, `maliev-staging`, `maliev-prod`

### Steps to Migrate
1. Ensure environment-specific secrets exist in GCP Secret Manager
2. Apply the new ArgoCD applications
3. Update application connection strings to environment-specific hosts
4. Remove old `maliev-infra` RabbitMQ deployment (if exists)

## Troubleshooting

### ExternalSecret Not Syncing
```bash
# Check ExternalSecret status
kubectl get externalsecrets -n maliev-dev
kubectl describe externalsecret shared-secrets -n maliev-dev

# Check if secret was created
kubectl get secret maliev-shared-secrets -n maliev-dev
```

### RabbitMQ Pod Not Starting
```bash
# Check pod status
kubectl get pods -n maliev-dev -l app.kubernetes.io/name=maliev-dev-rabbitmq

# Check pod logs
kubectl logs -n maliev-dev -l app.kubernetes.io/name=maliev-dev-rabbitmq

# Check RabbitMQ cluster status
kubectl get rabbitmqclusters -n maliev-dev
```

### Verify Secret Content
```bash
# Decode secret (check keys exist)
kubectl get secret maliev-shared-secrets -n maliev-dev -o jsonpath='{.data}' | jq
```

## Monitoring

Access RabbitMQ Management UI:
```bash
# Port forward to management UI
kubectl port-forward -n maliev-dev svc/rabbitmq 15672:15672
# Open browser to http://localhost:15672
```

Prometheus metrics are exposed on port `15692` at `/metrics`.
