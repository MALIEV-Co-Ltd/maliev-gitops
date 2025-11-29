# Redis Environment-Specific Deployments

## Architecture Decision

Redis is deployed **per environment** (development, staging, production) to provide:

- **Isolation**: Cache pollution in dev doesn't affect production
- **Security**: Separate data and access controls
- **Resource Optimization**: Tailored memory/cpu limits per environment
- **Configuration Flexibility**: Persistence settings can vary (e.g., no persistence in dev)

## Directory Structure

```
04-redis/
├── base/                           # Base configuration (shared)
│   ├── redis-statefulset.yaml     # Redis StatefulSet, Service, ConfigMap
│   └── kustomization.yaml         # Base kustomization
└── overlays/
    ├── development/               # Dev-specific settings
    │   └── kustomization.yaml     # 1 replica, 128Mi-512Mi memory, no persistence
    ├── staging/                   # Staging-specific settings
    │   └── kustomization.yaml     # 1 replica, 256Mi-1Gi memory
    └── production/                # Production-specific settings
        └── kustomization.yaml     # 1 replica (can scale), 512Mi-2Gi memory, AOF persistence
```

## Configuration per Environment

### Development (`maliev-dev` namespace)
- **Replicas**: 1
- **Memory**: 128Mi request, 512Mi limit
- **Storage**: 1Gi
- **Persistence**: No (save "")
- **Cluster Name**: `maliev-dev-redis`

### Staging (`maliev-staging` namespace)
- **Replicas**: 1
- **Memory**: 256Mi request, 1Gi limit
- **Storage**: 2Gi
- **Persistence**: No (save "")
- **Cluster Name**: `maliev-staging-redis`

### Production (`maliev-prod` namespace)
- **Replicas**: 1
- **Memory**: 512Mi request, 2Gi limit
- **Storage**: 5Gi
- **Persistence**: Yes (AOF enabled, fsync everysec)
- **Cluster Name**: `maliev-prod-redis`

## Service Access

Applications connect to Redis using:

### Development Environment
```
Host: redis.maliev-dev.svc.cluster.local
Port: 6379
```

### Staging Environment
```
Host: redis.maliev-staging.svc.cluster.local
Port: 6379
```

### Production Environment
```
Host: redis.maliev-prod.svc.cluster.local
Port: 6379
```

## ArgoCD Applications

Each environment has its own ArgoCD application:

- `argocd/environments/dev/redis.yaml` → Development
- `argocd/environments/staging/redis.yaml` → Staging
- `argocd/environments/prod/redis.yaml` → Production
