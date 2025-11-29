# RabbitMQ - MALIEV Infrastructure & Messaging Guide

Complete guide for RabbitMQ deployment and event-driven messaging in the MALIEV microservices platform.

## Table of Contents

### Infrastructure
1. [Prerequisites](#prerequisites)
2. [Deployment](#deployment)
3. [Service Endpoints](#service-endpoints)
4. [Management UI](#management-ui)
5. [Monitoring](#monitoring)
6. [Scaling](#scaling)
7. [Upgrades](#upgrades)
8. [Backup & Restore](#backup--restore)
9. [Troubleshooting](#troubleshooting)

### Messaging Architecture
10. [Message Naming Conventions](#message-naming-conventions)
11. [Exchange & Queue Topology](#exchange--queue-topology)
12. [Routing Patterns](#routing-patterns)
13. [Implementation Guide](#implementation-guide)
14. [Examples by Service](#examples-by-service)
15. [Architecture Diagrams](#architecture-diagrams)

### Quick Reference
16. [Common Commands](#common-commands)
17. [Code Snippets](#code-snippets)
18. [Best Practices](#best-practices)

---

# Infrastructure

## Prerequisites

### 1. Install the RabbitMQ Cluster Operator

The operator must be installed **once per cluster** before deploying RabbitMQ clusters:

```bash
# Install the latest version of the operator
kubectl apply -f "https://github.com/rabbitmq/cluster-operator/releases/latest/download/cluster-operator.yml"

# Verify the operator is running
kubectl get pods -n rabbitmq-system

# Expected output:
# NAME                                         READY   STATUS    RESTARTS   AGE
# rabbitmq-cluster-operator-xxxxxxxxxx-xxxxx   1/1     Running   0          30s
```

### 2. Create Required Secrets

The cluster requires credentials from `maliev-shared-secrets` in the `maliev-infra` namespace:

```yaml
apiVersion: v1
kind: Secret
metadata:
  name: maliev-shared-secrets
  namespace: maliev-infra
type: Opaque
stringData:
  RabbitMq__Username: "admin"
  RabbitMq__Password: "your-secure-password"
  RABBITMQ_ERLANG_COOKIE: "your-erlang-cookie"
```

**Important**: The Erlang cookie must be the same across all nodes for clustering.

---

## Deployment

### Deploy RabbitMQ Cluster

```bash
# Deploy to maliev-infra namespace
kubectl apply -k 1-cluster-infra/06-rabbitmq/base

# Verify the cluster is ready
kubectl get rabbitmqclusters -n maliev-infra
kubectl get pods -n maliev-infra -l app.kubernetes.io/name=maliev-rabbitmq

# Check cluster status
kubectl exec -it maliev-rabbitmq-server-0 -n maliev-infra -- rabbitmqctl cluster_status
```

### Scale to High Availability (Production)

```bash
# Scale to 3 replicas for HA
kubectl patch rabbitmqcluster maliev-rabbitmq -n maliev-infra --type merge -p '{"spec":{"replicas":3}}'

# Verify all nodes are clustered
kubectl exec -it maliev-rabbitmq-server-0 -n maliev-infra -- rabbitmqctl cluster_status
```

---

## Service Endpoints

The operator creates the following services in the `maliev-infra` namespace:

| Service Name | Purpose | Internal DNS | Port |
|--------------|---------|--------------|------|
| `maliev-rabbitmq-rabbitmq-client` | AMQP connections (primary) | `maliev-rabbitmq-rabbitmq-client.maliev-infra.svc.cluster.local` | 5672 |
| `rabbitmq` (alias) | Backward compatibility | `rabbitmq.maliev-infra.svc.cluster.local` | 5672 |
| `maliev-rabbitmq-rabbitmq` | Management UI & HTTP API | `maliev-rabbitmq-rabbitmq.maliev-infra.svc.cluster.local` | 15672 |

### Connection Strings

**For microservices (recommended - uses alias):**
```
amqp://<username>:<password>@rabbitmq.maliev-infra.svc.cluster.local:5672/
```

**For external applications:**
```
amqp://<username>:<password>@maliev-rabbitmq-rabbitmq-client.maliev-infra.svc.cluster.local:5672/
```

---

## Management UI

Access the RabbitMQ Management UI:

```bash
# Port-forward to local machine
kubectl port-forward service/maliev-rabbitmq-rabbitmq 15672:15672 -n maliev-infra

# Open browser to: http://localhost:15672
# Login with credentials from maliev-shared-secrets
```

---

## Monitoring

### Prometheus Metrics

Metrics are exposed on port `15692`:

```bash
# Port-forward to local machine
kubectl port-forward service/maliev-rabbitmq-rabbitmq 15692:15692 -n maliev-infra

# Test metrics endpoint
curl http://localhost:15692/metrics | grep rabbitmq_queue
```

### Key Metrics

```
# Queue depth
rabbitmq_queue_messages{queue="invoice-order-approved-queue"}

# Consumer count
rabbitmq_queue_consumer_count{queue="invoice-order-approved-queue"}

# Message rates
rate(rabbitmq_queue_messages_published_total[5m])

# Unacknowledged messages
rabbitmq_queue_messages_unacked
```

---

## Scaling

### Scale Up

```bash
kubectl patch rabbitmqcluster maliev-rabbitmq -n maliev-infra --type merge -p '{"spec":{"replicas":3}}'
```

### Scale Down

⚠️ **WARNING**: Can cause data loss if queues are not configured with high availability.

```bash
kubectl patch rabbitmqcluster maliev-rabbitmq -n maliev-infra --type merge -p '{"spec":{"replicas":2}}'
```

---

## Upgrades

```bash
# Update RabbitMQ version
kubectl patch rabbitmqcluster maliev-rabbitmq -n maliev-infra --type merge -p '{"spec":{"image":"rabbitmq:3.13-management-alpine"}}'

# Watch the rolling upgrade
kubectl get pods -n maliev-infra -l app.kubernetes.io/name=maliev-rabbitmq -w
```

---

## Backup & Restore

### Backup Definitions

```bash
kubectl exec -it maliev-rabbitmq-server-0 -n maliev-infra -- \
  rabbitmqctl export_definitions /tmp/definitions.json

kubectl cp maliev-infra/maliev-rabbitmq-server-0:/tmp/definitions.json ./rabbitmq-backup-$(date +%Y%m%d).json
```

### Restore Definitions

```bash
kubectl cp ./rabbitmq-backup.json maliev-infra/maliev-rabbitmq-server-0:/tmp/definitions.json

kubectl exec -it maliev-rabbitmq-server-0 -n maliev-infra -- \
  rabbitmqctl import_definitions /tmp/definitions.json
```

---

## Troubleshooting

### Check Status

```bash
kubectl get rabbitmqcluster maliev-rabbitmq -n maliev-infra -o yaml
kubectl get pods -n maliev-infra -l app.kubernetes.io/name=maliev-rabbitmq
```

### View Logs

```bash
kubectl logs -f maliev-rabbitmq-server-0 -n maliev-infra
```

### Common Issues

**Pods stuck in Pending**: Check PVC status
```bash
kubectl get pvc -n maliev-infra
```

**Auth failures**: Verify secret exists
```bash
kubectl get secret maliev-shared-secrets -n maliev-infra
```

---

# Messaging Architecture

## Message Naming Conventions

### Routing Key Pattern

All messages follow this pattern that **matches REST API structure**:

```
maliev.{service}.{version}.{entity}.{action}
```

**Matches REST API**: `/services/{service}/{version}/{entities}`

### Components

- **maliev**: Company namespace (fixed)
- **service**: Service name (singular, lowercase, e.g., `customer`, `order`)
- **version**: API version (e.g., `v1`, `v2`)
- **entity**: Business entity (singular, lowercase, e.g., `customer`, `delivery-address`)
- **action**: Past-tense verb (e.g., `created`, `updated`, `deleted`, `approved`)

### Naming Rules

- ✅ Use **dots (.)** between main components (required for RabbitMQ wildcards)
- ✅ Use **dashes (-)** for multi-word names (e.g., `delivery-address`, `line-item`)
- ✅ Use **singular** names
- ✅ Use **lowercase**

### REST API to Event Mapping

| HTTP Method | REST Endpoint | Event Routing Key |
|-------------|---------------|-------------------|
| POST | `/customers/v1/customers` | `maliev.customer.v1.customer.created` |
| PUT | `/customers/v1/customers/{id}` | `maliev.customer.v1.customer.updated` |
| POST | `/customers/v1/delivery-addresses` | `maliev.customer.v1.delivery-address.created` |
| PATCH | `/orders/v1/orders/{id}/approve` | `maliev.order.v1.order.approved` |
| POST | `/orders/v1/line-items` | `maliev.order.v1.line-item.added` |

### Examples

```
# Single-word entities
maliev.customer.v1.customer.created
maliev.order.v1.order.approved
maliev.invoice.v1.invoice.paid

# Multi-word entities (using dashes)
maliev.customer.v1.delivery-address.created
maliev.customer.v1.contact-person.added
maliev.order.v1.line-item.added
maliev.order.v1.shipping-label.generated
```

---

## Exchange & Queue Topology

### Exchange Strategy

We use **Topic Exchanges** for maximum flexibility:

```
Exchange: maliev.events (topic)
    │
    ├─ Binding: maliev.customer.v1.#         → Queue: customer-v1-all-events
    ├─ Binding: maliev.order.v1.#            → Queue: order-v1-all-events
    ├─ Binding: maliev.*.v1.*.created        → Queue: audit-all-v1-created-events
    └─ Binding: maliev.#                     → Queue: monitoring-all-events
```

### Standard Exchanges

| Exchange Name | Type | Purpose | Durability |
|---------------|------|---------|------------|
| `maliev.events` | topic | All business events | Durable |
| `maliev.commands` | topic | Command messages (RPC-style) | Durable |
| `maliev.dlx` | topic | Dead Letter Exchange (failed messages) | Durable |

### Queue Naming Convention

```
{service}-{entity}-{action}-queue
```

**Examples:**
- `customer-customer-created-queue`
- `customer-delivery-address-created-queue`
- `invoice-order-approved-queue`
- `notification-customer-created-queue`

---

## Routing Patterns

### Pattern 1: Exact Match

**Use Case**: InvoiceService listens only for order approvals.

```csharp
// Routing Key: maliev.order.v1.order.approved
// Queue: invoice-order-approved-queue
// Binding: maliev.order.v1.order.approved (exact match)
```

### Pattern 2: Wildcard - All Actions

**Use Case**: AuditService logs all customer entity events.

```csharp
// Routing Key: maliev.customer.v1.customer.*
// Queue: audit-customer-all-actions-queue
// Binding: maliev.customer.v1.customer.* (wildcard)
```

### Pattern 3: All Entities in Service Version

**Use Case**: DataWarehouse ingests all customer service v1 events.

```csharp
// Routing Key: maliev.customer.v1.#
// Queue: warehouse-customer-v1-all-queue
// Binding: maliev.customer.v1.# (multi-wildcard)
```

### Pattern 4: Cross-Service - All "created" Events

**Use Case**: AuditService logs all entity creations.

```csharp
// Routing Key: maliev.*.v1.*.created
// Queue: audit-all-created-events-queue
// Binding: maliev.*.v1.*.created (wildcard)
```

### Pattern 5: Monitor Everything

```csharp
// Routing Key: maliev.#
// Queue: monitoring-all-events-queue
// Binding: maliev.# (wildcard for everything)
```

---

## Implementation Guide

### Message Contract

```csharp
namespace Maliev.Messaging.Contracts.Customer;

/// <summary>
/// Event published when a new customer is created.
/// Routing Key: maliev.customer.v1.customer.created
/// REST Endpoint: POST /customers/v1/customers
/// </summary>
public sealed record CustomerCreatedEvent
{
    public required string MessageId { get; init; }
    public required DateTime Timestamp { get; init; }
    public required string EventType { get; init; } = "maliev.customer.v1.customer.created";
    public required string Version { get; init; } = "1.0";
    public required EventSource Source { get; init; }
    public required CustomerCreatedData Data { get; init; }
    public EventMetadata? Metadata { get; init; }
}

public sealed record CustomerCreatedData
{
    public required string CustomerId { get; init; }
    public required string Name { get; init; }
    public required string Email { get; init; }
}
```

### Publisher Implementation

```csharp
public interface IEventPublisher
{
    Task PublishAsync<T>(T @event, string routingKey, CancellationToken cancellationToken = default);
}

public sealed class RabbitMqEventPublisher : IEventPublisher
{
    private readonly IConnection _connection;
    private const string ExchangeName = "maliev.events";

    public async Task PublishAsync<T>(T @event, string routingKey, CancellationToken cancellationToken = default)
    {
        using var channel = _connection.CreateModel();

        var json = JsonSerializer.Serialize(@event);
        var body = Encoding.UTF8.GetBytes(json);

        var properties = channel.CreateBasicProperties();
        properties.Persistent = true;
        properties.ContentType = "application/json";

        channel.BasicPublish(
            exchange: ExchangeName,
            routingKey: routingKey,
            basicProperties: properties,
            body: body);

        await Task.CompletedTask;
    }
}
```

### Consumer Implementation

```csharp
public sealed class OrderApprovedConsumer : BackgroundService
{
    private const string ExchangeName = "maliev.events";
    private const string QueueName = "invoice-order-approved-queue";
    private const string RoutingKey = "maliev.order.v1.order.approved";

    protected override Task ExecuteAsync(CancellationToken stoppingToken)
    {
        _channel = _connection.CreateModel();

        _channel.QueueDeclare(QueueName, durable: true, exclusive: false, autoDelete: false);
        _channel.QueueBind(QueueName, ExchangeName, RoutingKey);
        _channel.BasicQos(prefetchSize: 0, prefetchCount: 10, global: false);

        var consumer = new EventingBasicConsumer(_channel);
        consumer.Received += async (model, ea) =>
        {
            try
            {
                var json = Encoding.UTF8.GetString(ea.Body.ToArray());
                var @event = JsonSerializer.Deserialize<OrderApprovedEvent>(json);
                
                await HandleEvent(@event);
                
                _channel.BasicAck(ea.DeliveryTag, multiple: false);
            }
            catch (Exception ex)
            {
                _logger.LogError(ex, "Error processing event");
                _channel.BasicNack(ea.DeliveryTag, multiple: false, requeue: false);
            }
        };

        _channel.BasicConsume(QueueName, autoAck: false, consumer: consumer);
        return Task.CompletedTask;
    }
}
```

---

## Examples by Service

### CustomerService

**Publishes:**
- `maliev.customer.v1.customer.created`
- `maliev.customer.v1.customer.updated`
- `maliev.customer.v1.customer.deleted`
- `maliev.customer.v1.delivery-address.created`
- `maliev.customer.v1.contact-person.added`

**Subscribes:**
- (None - CustomerService is a core service)

### OrderService

**Publishes:**
- `maliev.order.v1.order.created`
- `maliev.order.v1.order.approved`
- `maliev.order.v1.order.shipped`
- `maliev.order.v1.line-item.added`

**Subscribes:**
- `maliev.payment.v1.payment.confirmed` → Update order status
- `maliev.material.v1.material.allocated` → Confirm stock reservation

### InvoiceService

**Publishes:**
- `maliev.invoice.v1.invoice.created`
- `maliev.invoice.v1.invoice.paid`
- `maliev.invoice.v1.invoice.overdue`

**Subscribes:**
- `maliev.order.v1.order.approved` → Generate invoice
- `maliev.payment.v1.payment.confirmed` → Mark invoice as paid

### MaterialService

**Publishes:**
- `maliev.material.v1.material.created`
- `maliev.material.v1.material.stock-low`
- `maliev.material.v1.material.allocated`

**Subscribes:**
- `maliev.order.v1.order.approved` → Reserve inventory

### NotificationService

**Publishes:**
- `maliev.notification.v1.email.sent`
- `maliev.notification.v1.email.failed`

**Subscribes:**
- `maliev.customer.v1.customer.created` → Send welcome email
- `maliev.employee.v1.employee.created` → Send credentials
- `maliev.order.v1.order.shipped` → Send tracking notification

---

## Architecture Diagrams

### Message Flow: Order Approval

```
┌──────────────┐
│   Frontend   │
└──────┬───────┘
       │ PATCH /orders/v1/orders/{id}/approve
       ▼
┌─────────────────────────────────────────┐
│  OrderService                           │
│  1. Validate & approve order            │
│  2. Save to database                    │
│  3. Publish:                            │
│     maliev.order.v1.order.approved     │
└─────────────────┬───────────────────────┘
                  │
                  ▼
┌─────────────────────────────────────────┐
│   Exchange: maliev.events (Topic)       │
└──────────┬──────────────┬───────────────┘
           │              │
           ▼              ▼
    ┌──────────┐   ┌──────────┐
    │ Invoice  │   │ Material │
    │ Queue    │   │ Queue    │
    └────┬─────┘   └────┬─────┘
         │              │
         ▼              ▼
  ┌───────────┐  ┌────────────┐
  │ Invoice   │  │ Material   │
  │ Service   │  │ Service    │
  │ Creates   │  │ Reserves   │
  │ Invoice   │  │ Stock      │
  └───────────┘  └────────────┘
```

### Routing Key Matching

```
# Exact Match
Routing Key: maliev.customer.v1.customer.created
Binding:     maliev.customer.v1.customer.created
Result:      ✅ MATCH

# Single Wildcard (*)
Routing Key: maliev.customer.v1.customer.created
Binding:     maliev.customer.v1.customer.*
Result:      ✅ MATCH (matches "created")

# Multi Wildcard (#)
Routing Key: maliev.customer.v1.delivery-address.created
Binding:     maliev.customer.v1.#
Result:      ✅ MATCH (matches all customer v1 entities)

# Cross-Service Wildcard
Routing Key: maliev.order.v1.order.created
Binding:     maliev.*.v1.*.created
Result:      ✅ MATCH (matches all v1 "created" events)
```

---

# Quick Reference

## Common Commands

### Queue Management

```bash
# List all queues
kubectl exec -it maliev-rabbitmq-server-0 -n maliev-infra -- \
  rabbitmqctl list_queues name messages consumers

# List exchanges
kubectl exec -it maliev-rabbitmq-server-0 -n maliev-infra -- \
  rabbitmqctl list_exchanges name type durable

# List bindings
kubectl exec -it maliev-rabbitmq-server-0 -n maliev-infra -- \
  rabbitmqctl list_bindings

# Purge a queue (USE WITH CAUTION)
kubectl exec -it maliev-rabbitmq-server-0 -n maliev-infra -- \
  rabbitmqctl purge_queue <queue-name>
```

### User Management

```bash
# List users
kubectl exec -it maliev-rabbitmq-server-0 -n maliev-infra -- \
  rabbitmqctl list_users

# Add user
kubectl exec -it maliev-rabbitmq-server-0 -n maliev-infra -- \
  rabbitmqctl add_user <username> <password>

# Set permissions
kubectl exec -it maliev-rabbitmq-server-0 -n maliev-infra -- \
  rabbitmqctl set_permissions -p / <username> ".*" ".*" ".*"
```

---

## Code Snippets

### Declare Exchange and Queue

```csharp
channel.ExchangeDeclare(
    exchange: "maliev.events",
    type: ExchangeType.Topic,
    durable: true);

channel.QueueDeclare(
    queue: "invoice-order-approved-queue",
    durable: true,
    exclusive: false,
    autoDelete: false);

channel.QueueBind(
    queue: "invoice-order-approved-queue",
    exchange: "maliev.events",
    routingKey: "maliev.order.v1.order.approved");
```

### Publish Event

```csharp
var @event = new CustomerCreatedEvent
{
    MessageId = Guid.NewGuid().ToString(),
    Timestamp = DateTime.UtcNow,
    EventType = "maliev.customer.v1.customer.created",
    Data = new CustomerCreatedData { /* ... */ }
};

await _publisher.PublishAsync(
    @event,
    routingKey: "maliev.customer.v1.customer.created");
```

### Consume Event

```csharp
var consumer = new EventingBasicConsumer(_channel);
consumer.Received += async (model, ea) =>
{
    var json = Encoding.UTF8.GetString(ea.Body.ToArray());
    var @event = JsonSerializer.Deserialize<CustomerCreatedEvent>(json);
    
    await ProcessEvent(@event);
    
    _channel.BasicAck(ea.DeliveryTag, multiple: false);
};

_channel.BasicConsume(queueName, autoAck: false, consumer: consumer);
```

---

## Best Practices

### ✅ DO

- Use durable queues and exchanges for production
- Always version your message contracts
- Implement idempotent consumers
- Set appropriate prefetch counts (10-50 messages)
- Monitor queue depths and consumer lag
- Use Dead Letter Queues for error handling
- Log correlation IDs for distributed tracing
- Match routing keys to REST API structure

### ❌ DON'T

- Don't use auto-delete queues in production
- Don't share RabbitMQ channels between threads
- Don't forget to ACK/NACK messages
- Don't block consumer threads with long operations
- Don't use transient messages for critical data
- Don't expose RabbitMQ directly to the internet

---

## Wildcard Pattern Examples

```csharp
// All customer v1 events (any entity, any action)
maliev.customer.v1.#

// All customer entities (v1 only, any action)
maliev.customer.v1.customer.*

// All "created" events across all services (v1 only)
maliev.*.v1.*.created

// All events from all services
maliev.#

// All delivery-address events
maliev.customer.v1.delivery-address.*
```

---

## Resources

- [RabbitMQ Cluster Operator Documentation](https://www.rabbitmq.com/kubernetes/operator/operator-overview.html)
- [Operator GitHub Repository](https://github.com/rabbitmq/cluster-operator)
- [RabbitMQ Production Checklist](https://www.rabbitmq.com/production-checklist.html)
- [.NET RabbitMQ Client](https://www.rabbitmq.com/dotnet.html)
- [Topic Exchange Tutorial](https://www.rabbitmq.com/tutorials/tutorial-five-dotnet.html)
