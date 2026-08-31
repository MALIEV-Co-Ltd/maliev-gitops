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
2. bootstrap the reviewed PostgreSQL CONNECT/CREATE ACLs manually;
3. reconcile the exact admission-policy and migration foundation resources;
4. verify the existing application/database drift separately before minting a
   short-lived execution authorization.

This foundation does not create a canonical service database, mutate data or
schema, start a migration workload, or enable Argo auto-sync.

The provisioner RBAC and admission-policy copy is semantically pinned by tests
to `Legacy.Maliev.DataMigration` protected main. The current synchronized
source checkpoint is `3d1764f0046663b9b31eb38881f1a982beebea85`.
