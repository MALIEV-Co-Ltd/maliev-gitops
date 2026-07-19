# Dormant legacy identity and frontend cutover

This internal bundle pins the reviewed public service bases for AuthService,
EmployeeService, and the Intranet compatibility/BFF pair. The leading underscore
keeps it outside normal application structure discovery, and no active environment
or root ArgoCD kustomization references it.

The matching `argocd/environments/_disabled_apps/legacy` descriptors intentionally
have no automated sync, namespace creation option, or deletion finalizer. They are
validation inputs only and must not be moved into the active root configuration
until all of these owner gates are complete:

- publish and scan immutable images from the exact pinned commits;
- replace every zero digest in the rendered service bases with those reviewed
  registry digests;
- verify existing-cluster capacity without a new node pool or paid database;
- create the approved Workload Identity bindings and read back the redacted runtime
  secret projections from Secret Manager;
- complete Auth identity parity, Employee data/signature reconciliation, Intranet
  browser/session continuity, and the pinned Aspire owner review;
- capture the previous image and GitOps revisions, database recovery evidence, and
  a rehearsed rollback decision.

Activation and production deployment require a separate owner-approved pull request.
