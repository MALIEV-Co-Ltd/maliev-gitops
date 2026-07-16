# SearchService least-privilege secret projection

SearchService must receive validation and client-exchange material only. It must never
receive `maliev-shared-secrets` through `envFrom`, an RSA private key, a symmetric JWT
security key, or any equivalent token-signing material.

All SearchService ArgoCD Applications intentionally remain in
`argocd/environments/_disabled_apps`. This runbook does not authorize enabling, syncing,
applying, or deploying an Application.

## Runtime configuration boundary

The SearchService runtime consumes the following configuration through its current startup
registrations:

- `AddJwtAuthentication`: `Jwt__PublicKey`, `Jwt__Issuer`, `Jwt__Audience`;
- `AddPostgresDbContext<SearchDbContext>`: `ConnectionStrings__SearchDbContext`;
- `AddMassTransitWithRabbitMq`: `ConnectionStrings__rabbitmq`;
- `AddStandardCache`: `ConnectionStrings__redis`;
- `AddStandardCors`: `CORS__AllowedOrigins`;
- `AddAuthServiceTokenExchange`: the Search client ID and secret plus the AuthService HTTPS
  origin;
- `AddAuthServiceIAMClient`: the IAMService internal HTTPS origin.

The Deployment stores these reviewed non-secret values directly:

- `ServiceAuthentication__ClientId` (`service-search-service`);
- `Services__AuthService__BaseUrl` (the environment's canonical public HTTPS origin);
- `Services__IAMService__BaseUrl` (the internal HTTPS service origin);
- `ASPNETCORE_ENVIRONMENT`.

The SearchService ExternalSecret selects only these properties into the generated Secret:

- `Jwt__PublicKey`;
- `Jwt__Issuer`;
- `Jwt__Audience`;
- `ServiceAuthentication__ClientSecret`;
- `ConnectionStrings__SearchDbContext`;
- `ConnectionStrings__rabbitmq`;
- `ConnectionStrings__redis`;
- `CORS__AllowedOrigins`.

`dataFrom` is prohibited because it would project unrelated properties into the process.

## Required Google Secret Manager keys and properties

No secret values belong in this repository.

| Environment | Secret Manager key | Required properties |
| --- | --- | --- |
| Development | `maliev-dev-shared-config` | `Jwt__PublicKey`, `Jwt__Issuer`, `Jwt__Audience`, `CORS__AllowedOrigins`, `ConnectionStrings__rabbitmq`, `ConnectionStrings__redis` |
| Development | `maliev-dev-search-service-config` | `ConnectionStrings__SearchDbContext`, `ServiceAuthentication__ClientSecret` |
| Staging | `maliev-staging-shared-config` | `Jwt__PublicKey`, `Jwt__Issuer`, `Jwt__Audience`, `CORS__AllowedOrigins`, `ConnectionStrings__rabbitmq`, `ConnectionStrings__redis` |
| Staging | `maliev-staging-search-service-config` | `ConnectionStrings__SearchDbContext`, `ServiceAuthentication__ClientSecret` |
| Production | `maliev-prod-shared-config` | `Jwt__PublicKey`, `Jwt__Issuer`, `Jwt__Audience`, `CORS__AllowedOrigins`, `ConnectionStrings__rabbitmq`, `ConnectionStrings__redis` |
| Production | `maliev-prod-search-service-config` | `ConnectionStrings__SearchDbContext`, `ServiceAuthentication__ClientSecret` |

## Activation prerequisites

Before a future PR moves any SearchService Application out of `_disabled_apps`:

1. Populate every required property above through the approved secret-management process.
2. Verify the projected RSA public key matches the active AuthService signing key without
   exporting either key into logs or test artifacts.
3. Verify AuthService contains the `service-search-service` credential and IAM contains the
   `search-service` v1 workload profile with only `iam.auth.check-permission`.
4. Verify the AuthService origin presents valid HTTPS and is reachable from the Search
   namespace. Plain HTTP is rejected outside loopback development/testing.
5. Verify `https://maliev-iam-service:8080` is backed by namespace-local TLS whose certificate
   is valid for that host before activation. If the cluster does not provide that internal TLS
   boundary, keep SearchService disabled and use a separately reviewed canonical HTTPS route;
   do not weaken the runtime's HTTPS validation.
6. Verify the configured CORS origins are exact deployed application origins without
   wildcards, and verify the Search database, RabbitMQ, and Redis dependencies are present.
7. Render and validate without applying anything:

   ```text
   python scripts/check-search-service-secret-projection.py
   kustomize build 3-apps/maliev-search-service/overlays/development
   kustomize build 3-apps/maliev-search-service/overlays/staging
   kustomize build 3-apps/maliev-search-service/overlays/production
   ```

Application enablement, cluster sync, and production promotion require a separate reviewed
change after every prerequisite has evidence attached to the deployment-readiness tracker.
