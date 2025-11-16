# Staging Environment (maliev-staging)

⚠️ **STATUS: DISABLED** - Not yet deployed, infrastructure configured but not active.

## Infrastructure (Configured but Disabled)

The following infrastructure is **configured but commented out** in kustomization.yaml:

### Ready to Deploy (Currently Disabled)
- **Redis** - Distributed cache (1 instance, HA-ready)
- **RabbitMQ** - Message broker (1 instance, HA-ready)

### Enabled Components
- **PostgreSQL** - CloudNativePG cluster (configured)

## Activation Steps

When ready to activate staging:

1. **Add Secrets to Google Secret Manager**:
   - Create `maliev-staging-shared-config` secret
   - Include: RABBITMQ_USERNAME, RABBITMQ_PASSWORD, RABBITMQ_ERLANG_COOKIE

2. **Uncomment Infrastructure in kustomization.yaml**:
   ```yaml
   resources:
     - ../../1-cluster-infra/04-redis/base
     - ../../1-cluster-infra/06-rabbitmq/base
   ```

3. **Deploy Applications**: Move apps from `3-apps/_disabled_apps` or configure overlays

## Service Endpoints (when activated)
- Redis: `redis:6379` or `redis.maliev-staging.svc.cluster.local:6379`
- RabbitMQ AMQP: `rabbitmq:5672` or `rabbitmq.maliev-staging.svc.cluster.local:5672`
- RabbitMQ Management: `rabbitmq:15672` or `rabbitmq.maliev-staging.svc.cluster.local:15672`
- PostgreSQL: `postgres-cluster-rw:5432`
