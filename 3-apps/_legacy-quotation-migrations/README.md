# Dormant Quotation schema-migration plan

This overlay is an unreferenced, suspended plan for the existing
`legacy-postgres-main` cluster in `maliev-legacy`. It is **not** a deployment
resource. The active legacy environment does not include it, and every Job is
suspended with a non-routable immutable image digest.

The overlay proves the parts already owned by protected source code:

- two ordered invocations of the QuotationService migration runner;
- separate non-superuser, one-connection migration roles for `QuotationRequest`
  and `Quotation`, each inheriting only its database-owner role;
- credentials and the ECDSA public trust key projected from the single
  `maliev-legacy-secrets` Secret Manager JSON;
- tokenless, non-root, read-only Jobs with DNS/PostgreSQL-only egress;
- exact runner configuration and the required signed receipt resource name.

It deliberately does not define `legacy-quotation-schema-baseline-evidence`.
DataMigration protected main does not yet produce the exact signed schema-v1
envelope consumed by QuotationService, so creating a synthetic receipt here
would defeat the fail-closed gate. It also does not claim a snapshot gate:
the current runner has no contract that cryptographically binds a recoverable
PostgreSQL snapshot receipt to the migration. Merely mounting a file would be
security theatre.

Activation requires a separate reviewed change that:

1. adds the six pending properties to the existing consolidated secret;
2. publishes and independently verifies the exact schema-baseline producer;
3. adds a runner-enforced signed PostgreSQL snapshot/recovery gate;
4. creates the signed evidence resource without committing evidence or data;
5. replaces both placeholder digests with the scanned QuotationService
   migration image digest;
6. removes suspension only after DataMigration parity, Aspire validation,
   capacity evidence, and explicit owner approval;
7. replaces the environment's direct PostgreSQL overlay with this composed
   overlay for the bounded migration window (never render both).

No secret, database, cluster, or workload mutation is performed by committing
this dormant overlay.
