# Production Environment (maliev-prod)

⚠️ **STATUS: DISABLED** - Not yet deployed, infrastructure configured but not active.

**NOTE**: Do not confuse with `maliev` namespace (live production). This is the future production environment.

## Infrastructure (Configured but Disabled)

The following infrastructure is **configured but commented out** in kustomization.yaml:

### Ready to Deploy (Currently Disabled)
- **Redis** - Distributed cache (recommend 3 instances for HA in production)
- **RabbitMQ** - Message broker (recommend 3 instances for HA in production)

### Enabled Components
- **PostgreSQL** - CloudNativePG cluster (configured)

## Activation Steps

When ready to activate production:

1. **Add Secrets to Google Secret Manager**:
   - Create `maliev-prod-shared-config` secret
   - Include: RABBITMQ_USERNAME, RABBITMQ_PASSWORD, RABBITMQ_ERLANG_COOKIE
   - Use strong, production-grade credentials

2. **Scale for HA** (recommended for production):
   - Create overlays with `replicas: 3` for Redis and RabbitMQ
   - Ensure cluster has sufficient resources

3. **Uncomment Infrastructure in kustomization.yaml**:
   ```yaml
   resources:
     - ../../1-cluster-infra/04-redis/base
     - ../../1-cluster-infra/05-rabbitmq/base
   ```

4. **Deploy Applications**: Move apps from `3-apps/_disabled_apps` or configure overlays

## Production Considerations

- **HA Setup**: Run 3+ replicas for Redis and RabbitMQ
- **Resource Limits**: Review and adjust for production workloads
- **Monitoring**: Ensure Prometheus metrics are scraped
- **Backup**: Configure RabbitMQ persistence if needed
- **Security**: Rotate default credentials, use TLS

## Service Endpoints (when activated)
- Redis: `redis:6379` or `redis.maliev-prod.svc.cluster.local:6379`
- RabbitMQ AMQP: `rabbitmq:5672` or `rabbitmq.maliev-prod.svc.cluster.local:5672`
- RabbitMQ Management: `rabbitmq:15672` or `rabbitmq.maliev-prod.svc.cluster.local:15672`
- PostgreSQL: `postgres-cluster-rw:5432`
