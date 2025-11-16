# Development Environment (maliev-dev)

Active development environment for MALIEV microservices.

## Infrastructure

### Enabled Components
- **PostgreSQL** - CloudNativePG cluster (1 instance)
- **Redis** - Distributed cache (1 instance, HA-ready)
- **RabbitMQ** - Message broker (1 instance, HA-ready)

### Service Endpoints (within maliev-dev namespace)
- Redis: `redis:6379` or `redis.maliev-dev.svc.cluster.local:6379`
- RabbitMQ AMQP: `rabbitmq:5672` or `rabbitmq.maliev-dev.svc.cluster.local:5672`
- RabbitMQ Management: `rabbitmq:15672` or `rabbitmq.maliev-dev.svc.cluster.local:15672`
- PostgreSQL: `postgres-cluster-rw:5432`

## Secrets

Managed via External Secrets Operator from Google Secret Manager:
- **maliev-dev-shared-config**: Shared configuration including RabbitMQ credentials

## Scaling

Infrastructure is designed for HA but running single instances:
- To enable HA: Scale StatefulSets to 3 replicas
- Anti-affinity rules ensure distribution across nodes
- Headless services configured for cluster discovery
