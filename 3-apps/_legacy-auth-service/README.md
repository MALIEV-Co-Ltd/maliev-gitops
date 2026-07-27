# Legacy AuthService secret projection

This overlay is intentionally dormant. It documents the property-scoped projection
needed by `Legacy.Maliev.AuthService` while the Auth RefreshSessions database and its
Workload Identity binding are still being designed. It is not included by
`2-environments/4-legacy/kustomization.yaml`.

All values are read from the single `maliev-legacy-secrets` flat JSON payload. The
projection does not mount the entire bundle, and it does not contain refresh tokens,
cookies, or user-session identifiers. The Auth service receives the JWT private key;
other services must receive only the public key.

Do not activate this overlay until the RefreshSessions CNPG/database recovery and
rollback gates have passed and the `ConnectionStrings__RefreshSessions` template is
added with an approved database endpoint.
