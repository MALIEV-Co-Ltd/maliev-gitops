# Legacy MALIEV Order Service

This directory contains the dormant `maliev-legacy` runtime secret projection for
`Legacy.Maliev.OrderService`. It is deliberately excluded from the active environment
kustomization until database reconciliation, local Aspire validation, and the owner release
gate are complete.

The projection supplies only the two PostgreSQL connections, Redis connection, and JWT
verification material consumed by the migrated API. It does not contain a workload, Service,
signing key, storage credential, or source SQL Server configuration.
