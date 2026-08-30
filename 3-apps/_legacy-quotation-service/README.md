# Legacy MALIEV Quotation Service

This directory contains the dormant `maliev-legacy` runtime secret projection for
`Legacy.Maliev.QuotationService`. It is deliberately excluded from the active environment
kustomization until both database migration receipts, local Aspire validation, and the owner
release gate are complete.

The projection supplies the separate Quotation and QuotationRequest PostgreSQL connections,
Redis, JWT verification material, and the raw `legacy-quotation` service-client credential used
for Auth token exchange. The matching hash remains AuthService-only. No workload, Service,
signing key, storage credential, or source SQL Server configuration is included.
