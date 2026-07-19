# Legacy Redis

Resource-bounded, ephemeral Redis cache for legacy services in `maliev-legacy`. It contains no source-of-truth
data and can be recreated safely. Network policy allows only explicitly selected legacy service pods.

Redis requires the `legacy-redis-password` property from the single
`maliev-legacy-secrets` Secret Manager document. Both the server and the
container-local readiness probe receive that value through Secret references;
the password is never embedded in probe arguments or manifests. The current
server accepts RESP2 and RESP3. Protocol selection remains explicit in each
client so the owner can review and roll back protocol changes independently.
