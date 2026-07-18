# Legacy MALIEV Country Service

This internal-only deployment preserves the legacy Country API contract while the platform is migrated.
It reads the `Country` database through the resource-bounded `legacy-postgres-pooler-rw` PgBouncer
service backed by `legacy-postgres-main`, validates RSA access tokens, and uses the
ephemeral `legacy-redis` cache. The enclosing `maliev-legacy` Argo CD Application remains manual-sync
until the cluster capacity gate has passed.
