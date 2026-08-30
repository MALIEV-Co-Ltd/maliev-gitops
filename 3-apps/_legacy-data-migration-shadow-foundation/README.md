# Exact-25 shadow migration foundation

This Kustomize overlay is intentionally dormant. It is not referenced by the
`maliev-legacy` environment or any Argo CD Application. Rendering it prepares
the retained control database, unprivileged control and shadow roles,
consolidated-secret projections, and the reviewed fenced CNPG shadow
provisioner policy without creating an application workload.

Activation requires all of the following owner-approved operations in a
separate change:

1. add the four pending credential properties to `maliev-legacy-secrets`;
2. bootstrap the reviewed PostgreSQL CONNECT/CREATE ACLs manually;
3. approve the cluster-scoped admission-policy allowance in the Argo project;
4. replace the environment's direct PostgreSQL overlay reference with this
   composed overlay only for the bounded migration window (never render both).

This foundation does not create a canonical service database, mutate data or
schema, start a migration workload, or enable Argo auto-sync.
