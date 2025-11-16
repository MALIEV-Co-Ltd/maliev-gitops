# Redis Infrastructure

Shared Redis cache for MALIEV microservices.

## Configuration

- **Image**: redis:7.2-alpine
- **Replicas**: 1 (single instance)
- **Memory Limit**: 512Mi with LRU eviction at 256MB
- **Storage**: 1Gi persistent volume
- **Namespace**: maliev-infra

## Service Endpoint

Redis is accessible within the cluster at:
- `redis.maliev-infra.svc.cluster.local:6379`
- Short name: `redis` (from within maliev-infra namespace)

## Usage

Services should configure Redis connection string:
```
redis.maliev-infra.svc.cluster.local:6379
```

## Notes

- Persistence disabled (cache only mode)
- LRU eviction policy when memory limit reached
- Health checks via TCP and redis-cli ping
