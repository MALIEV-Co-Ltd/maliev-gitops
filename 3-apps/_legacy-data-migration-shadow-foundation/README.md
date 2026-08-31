# Exact-25 shadow migration foundation

This Kustomize overlay is activated by the database-only `maliev-legacy`
environment for the owner-approved exact-25 shadow validation window. Rendering
the overlay by itself prepares only the retained control database, consolidated
secret projections, and the reviewed fenced CNPG shadow provisioner policy. The
environment applies the two unprivileged managed-role patches to its existing
single CloudNativePG Cluster render, so activating this overlay cannot duplicate
or independently reconcile the PostgreSQL estate.

Execution still requires all of the following owner-approved operations:

1. retain the four migration credential properties in `maliev-legacy-secrets`;
2. bootstrap the reviewed PostgreSQL CONNECT/CREATE ACLs manually, preserving
   the CloudNativePG `streaming_replica` connection described below;
3. reconcile the exact admission-policy and migration foundation resources;
4. verify the existing application/database drift separately before minting a
   short-lived execution authorization.

This foundation does not create a canonical service database, mutate data or
schema, start a migration workload, or enable Argo auto-sync.

## Manual PostgreSQL ACL contract

The administrative database is `postgres`. Its default `PUBLIC` `CONNECT` must
be revoked, while explicit `CONNECT` remains granted to both the narrowly scoped
`legacy_migration_shadow` role and CloudNativePG's internal
`streaming_replica` role. Revoking the internal grant prevents the replica
instance manager from reconnecting and is not an approved migration boundary.
The shadow role receives no `CREATE` privilege on `postgres` and remains
`NOCREATEDB`; it can reach only `postgres` and run-owned databases named
`legacy_shadow_*`. The control role receives only `CONNECT` and `CREATE` on
`legacy_migration_control`. `PUBLIC` remains denied on `postgres`,
`template1`, `legacy_migration_control`, every canonical database, and every
run-owned shadow database.

The owner-reviewed bootstrap must therefore preserve this exact administrative
database boundary:

```sql
REVOKE CONNECT ON DATABASE postgres FROM PUBLIC;
GRANT CONNECT ON DATABASE postgres TO streaming_replica;
GRANT CONNECT ON DATABASE postgres TO legacy_migration_shadow;
REVOKE CREATE ON DATABASE postgres FROM legacy_migration_shadow;
```

The operator must verify the existing `streaming_replica` role before running
the grants and must fail closed if any named role or database differs. This
documentation is a contract only; GitOps does not execute these SQL statements.

The admission policy permits the exact `legacy-postgres-main` service account to
perform `UPDATE` only when the complete Database `spec`, labels, annotations,
owner references, and fencing remain equivalent. The controller may add or remove
only its `cnpg.io/deleteDatabase` finalizer; every other finalizer is preserved.
This admits CNPG-owned finalizer and status reconciliation, including status
updates after connections are enabled, but denies controller creation, deletion,
or migration-state changes. The provisioner RBAC and admission-policy copy is semantically pinned by tests
to `Legacy.Maliev.DataMigration` protected main. The current synchronized
source checkpoint is `f9cb90a622e7d680ccbd9d64cb1922c3ed2b7594`.
