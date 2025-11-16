# RabbitMQ Infrastructure

Shared message broker for MALIEV microservices event-driven architecture.

## Configuration

- **Image**: rabbitmq:3.12-management-alpine
- **Replicas**: 1 (single instance)
- **Memory Limit**: 1Gi with 60% high watermark
- **Storage**: 5Gi persistent volume
- **Namespace**: maliev-infra
- **Plugins**: rabbitmq_management, rabbitmq_prometheus

## Service Endpoints

RabbitMQ is accessible within the cluster at:
- **AMQP**: `rabbitmq.maliev-infra.svc.cluster.local:5672`
- **Management UI**: `rabbitmq.maliev-infra.svc.cluster.local:15672`

## Default Credentials

- **Username**: maliev
- **Password**: maliev123

**WARNING**: Change these credentials in production using External Secrets.

## Connection String Format

For MassTransit/RabbitMQ clients:
```
rabbitmq://rabbitmq.maliev-infra.svc.cluster.local:5672
```

With credentials:
```
rabbitmq://maliev:maliev123@rabbitmq.maliev-infra.svc.cluster.local:5672
```

## Usage in Services

Configure RabbitMQ connection in appsettings:
```json
{
  "RabbitMQ": {
    "Enabled": true,
    "Host": "rabbitmq.maliev-infra.svc.cluster.local",
    "Port": 5672,
    "Username": "maliev",
    "Password": "maliev123",
    "VirtualHost": "/"
  }
}
```

## Management UI

Access the management UI by port-forwarding:
```bash
kubectl port-forward -n maliev-infra svc/rabbitmq 15672:15672
```

Then visit: http://localhost:15672

## Notes

- Single instance (not clustered)
- Management plugin enabled for monitoring
- Prometheus metrics available at `:15672/metrics`
- Health checks via rabbitmq-diagnostics
