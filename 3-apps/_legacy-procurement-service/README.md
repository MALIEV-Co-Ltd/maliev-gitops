# Legacy MALIEV Procurement Service

This directory contains the dormant `maliev-legacy` runtime secret projection for
`Legacy.Maliev.ProcurementService`. It is deliberately excluded from the active environment
kustomization until database reconciliation, local Aspire validation, and the owner release
gate are complete.

The projection preserves the separate Supplier and PurchaseOrder PostgreSQL connections and
supplies Redis and JWT verification material. It does not contain a workload, Service, signing
key, storage credential, or source SQL Server configuration.
