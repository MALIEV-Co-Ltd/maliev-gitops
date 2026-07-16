# ContactService least-privilege secret projection

ContactService must receive validation and client-exchange material only. It must never
receive `maliev-shared-secrets` through `envFrom`, an RSA private key, a symmetric JWT
security key, or any equivalent token-signing material.

All ContactService ArgoCD Applications intentionally remain in
`argocd/environments/_disabled_apps`. This runbook does not authorize enabling, syncing,
or applying an Application.

## Runtime configuration boundary

The Deployment stores these non-secret values directly:

- `Services__AuthService__BaseUrl`
- `ServiceAuthentication__ClientId`
- `ExternalServices__UploadService`
- `ExternalServices__CountryService`

The ContactService ExternalSecret selects only these properties into the generated
Kubernetes Secret:

- `Jwt__PublicKey`
- `Jwt__Issuer`
- `Jwt__Audience`
- `ServiceAuthentication__ClientSecret`
- `ConnectionStrings__ContactDbContext`
- `ConnectionStrings__rabbitmq`
- `ConnectionStrings__redis`
- `CORS__AllowedOrigins`

The complete JWT verifier trust tuple, CORS origins, RabbitMQ, and Redis properties are
selected from each environment's existing shared configuration object. The Contact database
and service client secret are selected from the existing ContactService configuration object.
`dataFrom` is prohibited because it would project unrelated properties into the workload.

## Required Google Secret Manager keys and properties

No values belong in this repository.

| Environment | Secret Manager key | Required properties |
| --- | --- | --- |
| Development | `maliev-dev-shared-config` | `Jwt__PublicKey`, `Jwt__Issuer`, `Jwt__Audience`, `CORS__AllowedOrigins`, `ConnectionStrings__rabbitmq`, `ConnectionStrings__redis` |
| Development | `maliev-dev-contact-service-config` | `ConnectionStrings__ContactDbContext`, `ServiceAuthentication__ClientSecret` |
| Staging | `maliev-staging-shared-config` | `Jwt__PublicKey`, `Jwt__Issuer`, `Jwt__Audience`, `CORS__AllowedOrigins`, `ConnectionStrings__rabbitmq`, `ConnectionStrings__redis` |
| Staging | `maliev-staging-contact-service-config` | `ConnectionStrings__ContactDbContext`, `ServiceAuthentication__ClientSecret` |
| Production | `maliev-prod-shared-config` | `Jwt__PublicKey`, `Jwt__Issuer`, `Jwt__Audience`, `CORS__AllowedOrigins`, `ConnectionStrings__rabbitmq`, `ConnectionStrings__redis` |
| Production | `maliev-prod-contact-service-config` | `ConnectionStrings__ContactDbContext`, `ServiceAuthentication__ClientSecret` |

## Activation prerequisites

Before a future PR moves any ContactService Application out of `_disabled_apps`:

1. Populate every required property above through the approved secret-management process.
   The current inventory requires adding the Contact client-secret property in every
   environment and adding the verifier trust tuple, CORS, RabbitMQ, and Redis properties
   where they are absent, including staging and production.
2. Verify the projected RSA public key matches the active AuthService signing key without
   exporting either key into logs or test artifacts.
3. Verify AuthService has the `service-contact-service` client and its scoped IAM workload
   principal before providing the corresponding ContactService client secret.
4. Verify the environment's HTTPS AuthService origin is reachable from the ContactService
   namespace and presents a valid certificate. Service token exchange rejects non-loopback
   plain HTTP outside local tests.
5. Verify the configured CORS origins are the deployed customer application origins for the
   environment. Do not broaden them with wildcards.
6. Verify the namespace-local UploadService, CountryService, RabbitMQ, Redis, and database
   dependencies are present and authorized.
7. Render and validate without applying anything:

   ```text
   python scripts/check-contact-service-secret-projection.py
   kustomize build 3-apps/maliev-contact-service/overlays/development
   kustomize build 3-apps/maliev-contact-service/overlays/staging
   kustomize build 3-apps/maliev-contact-service/overlays/production
   ```

Application enablement, cluster sync, and production promotion require a separate reviewed
change after these prerequisites have evidence attached to the deployment-readiness tracker.
