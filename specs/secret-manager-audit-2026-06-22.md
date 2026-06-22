# Secret Manager Audit - 2026-06-22

This audit compares `maliev-gitops` `ExternalSecret` references with Google Secret Manager in project `maliev-website`.

No secret values are stored in this file. Key presence and required follow-up only.

## Changes Applied

- Created `maliev-dev-delivery-service-config` in Google Secret Manager with SHIPPOP dev configuration keys only.
- Updated `maliev-dev-delivery-service-config` with the documented SHIPPOP dev public tracking base URL in `Shippop__InternationalBaseUrl`; secret values were preserved and not recorded.
- Created and verified the live development database `delivery_app_db`, then updated `maliev-dev-delivery-service-config` with `ConnectionStrings__DeliveryDbContext`; secret values were preserved and not recorded.
- Updated `maliev-dev-delivery-service-config` with the documented HTTPS SHIPPOP dev domestic base URL in `Shippop__DomesticBaseUrl`; secret values were preserved and not recorded.
- Verified a live SHIPPOP dev `/pricelist/` request with the stored dev key, HTTPS base URL, JSON payload, and string `courier_code`; SHIPPOP returned success for `EMST`.
- Built and published dev DeliveryService image tag `bcefbbec021165c6f6e865649eed2850868aa2bb`, verified in Artifact Registry at digest `sha256:19ff346c90740919d8baab646654407f29275a72f1c0f4bf8e45999f7bbee6bf`.
- Moved the dev DeliveryService ArgoCD Application back under `argocd/environments/dev/apps` after verifying the image includes the SHIPPOP integration commits.
- Named the DeliveryService Kubernetes Service port `http` so the dev ServiceMonitor can resolve its `port: http` endpoint when the app is activated.
- Verified the previously referenced dev DeliveryService image tags `b4a0d4a9af701afb6da499c46e7bafba39f5fb3e` and `1d03d045ea20d005060662fd5294e97e5c4bac32` should not be used for current SHIPPOP dev testing; the first predates the SHIPPOP gateway commits, and the second predates the `/pricelist/` payload fix.
- Added a reusable local redacted audit helper at `B:\maliev\.agents\skills\maliev-secret-manager-audit\scripts\audit-secret-refs.ps1` and documented it in the local `maliev-secret-manager-audit` skill. The helper compares names only and does not print secret payload values.
- Corrected DeliveryService production overlay from `maliev-production-delivery-service-config` to `maliev-prod-delivery-service-config`.
- Corrected NotificationService GitOps from legacy individual remote refs (`maliev-email-service-db-connection-string`, `redis-connection-string`, `rabbitmq-connection-string`) to environment-specific config extraction:
  - `maliev-dev-notification-service-config`
  - `maliev-staging-notification-service-config`
  - `maliev-prod-notification-service-config`
- Corrected GeometryService GitOps from legacy individual remote refs (`rabbitmq-connection-string`, `jwt-public-key`, `jwt-private-key`, `jwt-security-key`, `jwt-issuer`, `jwt-audience`) to environment-specific config extraction:
  - `maliev-dev-geometry-service-config`
  - `maliev-staging-geometry-service-config`
  - `maliev-prod-geometry-service-config`
- Created `maliev-dev-geometry-service-config` from existing `maliev-dev-shared-config` values, mapping them to GeometryService's uppercase environment variable names. The dev GeometryService secret includes `RABBITMQ_URI`, JWT validation keys, an intentionally empty `JWT_PRIVATE_KEY`, and `ASPNETCORE_ENVIRONMENT`/`ENVIRONMENT` set to `Development` so the service's own HS256 development fallback is allowed.
- Removed stale disabled `maliev-email-service.yaml` Application manifests that duplicated NotificationService app names and paths while pointing at an old repository URL.
- Corrected disabled Application source paths that pointed at nonexistent overlays:
  - production `maliev-compensation-service`, `maliev-compliance-service`, `maliev-leave-service`, `maliev-lifecycle-service`, and `maliev-performance-service` now use `overlays/production` instead of `overlays/prod`
  - staging/production MaterialService now uses `3-apps/maliev-material-service` instead of `3-apps/material-service`
- Removed disabled `maliev-quotationrequest-service` Application manifests because the `Maliev.QuotationRequestService` repo and `3-apps/maliev-quotationrequest-service` GitOps app directory are absent. Existing `maliev-<env>-quotationrequest-service-config` Secret Manager entries remain as unreferenced legacy configs pending an explicit retention/deletion decision.
- Corrected chatbot overlays to consume existing LINE chatbot secrets:
  - `maliev-dev-line-chatbot-service-config`
  - `maliev-staging-line-chatbot-service-config`
  - `maliev-prod-line-chatbot-service-config`

## Verified Existing DeliveryService Dev Secret Keys

`maliev-dev-delivery-service-config` currently contains:

- `ConnectionStrings__DeliveryDbContext`
- `Shippop__DomesticApiKey`
- `Shippop__DomesticBaseUrl`
- `Shippop__DomesticEmail`
- `Shippop__InternationalBaseUrl`
- `Shippop__InternationalBearerToken`

`Shippop__InternationalBearerToken` is currently empty. The public tracking endpoint does not require it, but shipment creation through SHIPPOP Inter still needs a confirmed bearer token before enablement.

It now contains `ConnectionStrings__DeliveryDbContext` for the verified development database `delivery_app_db`.

DeliveryService code currently uses `Shippop__DomesticApiKey` and `Shippop__DomesticBaseUrl` for SHIPPOP domestic rates, `Shippop__InternationalBaseUrl` for SHIPPOP Inter public price/tracking endpoints, and does not require `Shippop__InternationalBearerToken` for those public endpoints. `GoShip__AppId` and `GoShip__Secret` are only required when GoShip fallback calls are invoked.

## Verified Shared Config Key Shape

The app deployments generally consume both `maliev-shared-secrets` and their service-specific secret through `envFrom`.

Redacted key inspection showed:

- `maliev-dev-shared-config` contains Redis, RabbitMQ, CORS, and JWT keys:
  - `ConnectionStrings__rabbitmq`
  - `ConnectionStrings__redis`
  - `CORS__AllowedOrigins`
  - `Jwt__Audience`
  - `Jwt__Issuer`
  - `Jwt__PublicKey`
  - `Jwt__SecurityKey`
  - `RABBITMQ_ERLANG_COOKIE`
  - `RabbitMq__Password`
  - `RabbitMq__Username`
- `maliev-staging-shared-config` currently contains only JWT keys:
  - `Jwt__Audience`
  - `Jwt__Issuer`
  - `Jwt__SecurityKey`
- `maliev-prod-shared-config` currently contains only JWT keys:
  - `Jwt__Audience`
  - `Jwt__Issuer`
  - `Jwt__SecurityKey`

Staging and production shared config may still need Redis/RabbitMQ/CORS keys if the cluster deployments are expected to start the same way as development.

## Verified Environment Deployment State

Live Kubernetes metadata and GitOps environment kustomizations currently show:

- `maliev-dev` has synced ExternalSecrets for:
  - `postgres-app-credentials`
  - `postgres-superuser-credentials`
  - `maliev-shared-secrets`
- `maliev-dev` has live service aliases for:
  - `postgres-cluster-rw`
  - `redis`
  - `rabbitmq`
- `maliev-staging` and `maliev-prod` namespaces exist, but currently have no app/shared/database ExternalSecrets synced.
- `2-environments/2-staging/kustomization.yaml` and `2-environments/3-production/kustomization.yaml` currently leave `secrets.yaml`, shared secrets, common apps, database, Redis, and RabbitMQ resources commented out.
- `maliev-staging-pg-app-password`, `maliev-staging-pg-superuser-password`, `maliev-prod-pg-app-password`, and `maliev-prod-pg-superuser-password` are referenced by GitOps `secrets.yaml` files but do not currently exist in Google Secret Manager.
- `kubectl kustomize 2-environments/2-staging` and `kubectl kustomize 2-environments/3-production` currently render without those PostgreSQL ExternalSecrets because the relevant resources are disabled in each environment kustomization.
- The missing staging/prod PostgreSQL Secret Manager entries are therefore activation prerequisites for those environment resources, not currently rendered live deployment dependencies.
- `argocd/environments/dev/apps` currently includes `maliev-dev-environment`, pointing at `2-environments/1-development`, and `maliev-delivery-service-dev`, pointing at `3-apps/maliev-delivery-service/overlays/development`.
- The active app-of-apps manifests under `argocd/environments/staging/apps` and `argocd/environments/prod/apps` currently include only each environment Application, pointing at `2-environments/2-staging` and `2-environments/3-production`.
- Individual service Application manifests for DeliveryService staging/prod, GeometryService, NotificationService, QuoteEngine, AccountingService, CommerceService, FacilityService, IAMService, RegistryService, SearchService, and the other services are currently under `argocd/environments/_disabled_apps`. DeliveryService dev is active.
- `argocd/environments/live/maliev-live-environment.yaml` points to `2-environments/0-live-production`, and that kustomization currently renders namespace and ingress only. It does not render service deployments or ExternalSecrets.
- A live cluster check returned zero ArgoCD `Application` resources through `kubectl get applications -n argocd`; treat this repo audit as desired-state evidence unless ArgoCD access/state is confirmed separately.
- Disabled NotificationService manifests are now represented by `maliev-notification-service.yaml` only; stale duplicate `maliev-email-service.yaml` files were removed from dev/staging/prod disabled app folders.
- Disabled app source paths were scanned for missing target overlays. The stale `maliev-quotationrequest-service` dev/staging/prod manifests were removed because there is no matching `3-apps/maliev-quotationrequest-service` directory and no `Maliev.QuotationRequestService` repo in the workspace.
- `3-apps/_common` currently applies common labels only. It does not include service deployments. The dev environment renders namespace, ingress, configmap, environment/shared secrets, and database resources; DeliveryService dev is active through its individual Application and references a SHIPPOP-inclusive image.
- The legacy unreferenced `maliev-<env>-email-service-config` Secret Manager entries currently contain empty JSON objects and cannot be safely copied to satisfy `maliev-<env>-notification-service-config`. NotificationService requires a confirmed `ConnectionStrings__NotificationDbContext`, encryption key, and any intended provider keys before enablement.

Current development PostgreSQL databases observed from the live `maliev-dev` Postgres cluster:

- `app_db`
- `auth_app_db`
- `career_app_db`
- `contact_app_db`
- `contact_app_test_db`
- `country_app_db`
- `currency_app_db`
- `customer_app_db`
- `delivery_app_db`
- `employee_app_db`
- `employee_service_db`
- `invoice_app_db`
- `material_app_db`
- `order_app_db`
- `payment_app_db`
- `postgres`
- `purchaseorder_app_db`
- `supplier_app_db`
- `supplier_service_db`
- `upload_app_db`

The live development cluster does not currently show databases for the missing service config families listed below, including accounting, commerce, facility, IAM, registry, and search. Do not create connection strings for those services until the target databases and credentials are created or otherwise confirmed. DeliveryService is no longer part of this missing development database list, and its dev ArgoCD Application is active with a SHIPPOP-inclusive image containing the verified `/pricelist/` payload fix.

## Confirmed Required Service-Specific Keys

These keys were derived from each service's startup/configuration code and current appsettings shape. Values are intentionally not recorded here.

| Service secret family | Confirmed service-specific keys |
| --- | --- |
| `maliev-<env>-accounting-service-config` | `ConnectionStrings__AccountingDbContext` |
| `maliev-<env>-commerce-service-config` | `ConnectionStrings__CommerceDbContext` |
| `maliev-<env>-contact-service-config` | `ConnectionStrings__ContactDbContext` |
| `maliev-<env>-delivery-service-config` | Startup and SHIPPOP dev quotes/tracking: `ConnectionStrings__DeliveryDbContext`, `Shippop__DomesticBaseUrl`, `Shippop__DomesticApiKey`, `Shippop__DomesticEmail`, `Shippop__InternationalBaseUrl`. SHIPPOP Inter authenticated shipment creation: `Shippop__InternationalBearerToken`. GoShip fallback: `GoShip__BaseUrl`, `GoShip__AppId`, `GoShip__Secret`. |
| `maliev-<env>-facility-service-config` | `ConnectionStrings__FacilityDbContext` |
| `maliev-<env>-geometry-service-config` | `RABBITMQ_URI`, `JWT_PUBLIC_KEY`, `JWT_PRIVATE_KEY`, `JWT_SECURITY_KEY`, `JWT_ISSUER`, `JWT_AUDIENCE` |
| `maliev-<env>-iam-service-config` | `ConnectionStrings__IamDbContext` |
| `maliev-<env>-notification-service-config` | `ConnectionStrings__NotificationDbContext` |
| `maliev-<env>-quote-engine-config` | `Web__BaseUrl`, `QuoteEngine__BaseUrl`, `GoogleMaps__BrowserApiKey` if Google Maps is enabled for that environment; service endpoint overrides may also be needed when Aspire service discovery is not available |
| `maliev-<env>-registry-service-config` | `ConnectionStrings__RegistryDbContext`, optional provider keys `BDEX__ConsumerKey` and `BDEX__ConsumerSecret` if BDEX is enabled |
| `maliev-<env>-search-service-config` | `ConnectionStrings__SearchDbContext` |

Notes:

- Existing `maliev-dev-contact-service-config` contains only `ConnectionStrings__ContactDbContext`, which matches the current minimum service-specific requirement.
- Existing `maliev-dev-order-service-config` shows the established pattern of service-specific DB connection strings plus external service endpoint overrides.
- Existing `maliev-dev-delivery-service-config` contains the keys required for DeliveryService database startup, SHIPPOP domestic rate quotes, SHIPPOP Inter public rates, and SHIPPOP public tracking. It does not contain GoShip fallback credentials.
- Existing `maliev-dev-geometry-service-config` contains the keys required for GeometryService dev startup and auth: `RABBITMQ_URI`, `JWT_PUBLIC_KEY`, `JWT_SECURITY_KEY`, `JWT_ISSUER`, `JWT_AUDIENCE`, `JWT_PRIVATE_KEY`, `ASPNETCORE_ENVIRONMENT`, and `ENVIRONMENT`. `JWT_PRIVATE_KEY` is intentionally empty in dev because GeometryService allows HS256 service-account signing only when its environment is Development or Testing.
- Existing `maliev-<env>-email-service-config` entries are empty JSON objects. They are stale placeholders, not migration sources for NotificationService.
- `ConnectionStrings__IamDbContext` uses the casing from `Maliev.IAMService.Api/Program.cs`.
- Do not infer DB names, usernames, or passwords from neighboring services. Create or update these Secret Manager entries only with confirmed environment-specific values.

## Missing GitOps References In Google Secret Manager

These `3-apps/*/overlays/*/service-secrets-patch.yaml` references do not currently exist in Google Secret Manager:

### Development

- `maliev-dev-accounting-service-config`
- `maliev-dev-commerce-service-config`
- `maliev-dev-facility-service-config`
- `maliev-dev-iam-service-config`
- `maliev-dev-notification-service-config`
- `maliev-dev-quote-engine-config`
- `maliev-dev-registry-service-config`
- `maliev-dev-search-service-config`

### Staging

- `maliev-staging-accounting-service-config`
- `maliev-staging-commerce-service-config`
- `maliev-staging-contact-service-config`
- `maliev-staging-delivery-service-config`
- `maliev-staging-facility-service-config`
- `maliev-staging-geometry-service-config`
- `maliev-staging-iam-service-config`
- `maliev-staging-notification-service-config`
- `maliev-staging-quote-engine-config`
- `maliev-staging-registry-service-config`
- `maliev-staging-search-service-config`

### Production

- `maliev-prod-accounting-service-config`
- `maliev-prod-commerce-service-config`
- `maliev-prod-contact-service-config`
- `maliev-prod-delivery-service-config`
- `maliev-prod-facility-service-config`
- `maliev-prod-geometry-service-config`
- `maliev-prod-iam-service-config`
- `maliev-prod-notification-service-config`
- `maliev-prod-quote-engine-config`
- `maliev-prod-registry-service-config`
- `maliev-prod-search-service-config`

## Deployment Activation Classification

Current GitOps desired-state structure separates the missing service config secrets into these operational buckets:

Latest redacted validator run on 2026-06-22 reported:

- 4 active ArgoCD Applications.
- 0 active app overlay service config secret names missing in Secret Manager.
- 30 disabled app overlay service config secret names missing in Secret Manager.
- 30 missing app overlay service config secret names in Secret Manager.
- 0 disabled ArgoCD app source paths missing.
- 0 duplicate disabled ArgoCD app names.
- 4 missing staging/prod PostgreSQL environment `remoteRef` secret names, all currently disabled by environment kustomizations.
- 14 existing service config secrets in Secret Manager that are not referenced by current app overlays.

### Active Environment Prerequisites

These are active environment-level prerequisites or rendered resources:

- `maliev-dev-shared-config`
- `maliev-dev-pg-credentials`
- `maliev-staging-shared-config`
- `maliev-prod-shared-config`

Development shared/PostgreSQL secrets are synced in the live `maliev-dev` namespace. Staging/prod shared configs exist in Secret Manager, but staging/prod environment kustomizations currently do not render shared/database/app resources.

### Disabled App Prerequisites

The missing service config secrets listed in the Development, Staging, and Production sections above are referenced by app overlay manifests, but none are currently referenced by active app-of-apps service Applications. They are disabled-app prerequisites: the corresponding individual ArgoCD service Application manifests are currently under `argocd/environments/_disabled_apps`.

Create those service config secrets before moving the corresponding Application manifest out of `_disabled_apps` or adding the app overlay to an active app-of-apps path.

## Existing Secret Manager Entries Not Referenced By App Overlays

These service config secrets exist but are not referenced by current app overlay `service-secrets-patch.yaml` files:

### Development

- `maliev-dev-email-service-config`
- `maliev-dev-log-service-config`
- `maliev-dev-orderstatus-service-config`
- `maliev-dev-quotationrequest-service-config`

### Staging

- `maliev-staging-email-service-config`
- `maliev-staging-log-service-config`
- `maliev-staging-message-service-config`
- `maliev-staging-orderstatus-service-config`
- `maliev-staging-quotationrequest-service-config`

### Production

- `maliev-prod-email-service-config`
- `maliev-prod-log-service-config`
- `maliev-prod-message-service-config`
- `maliev-prod-orderstatus-service-config`
- `maliev-prod-quotationrequest-service-config`

Redacted payload inspection of the unreferenced service config secrets showed:

- `maliev-<env>-email-service-config` entries are empty JSON objects and should not be treated as valid NotificationService config.
- `maliev-<env>-log-service-config`, `maliev-<env>-message-service-config`, and `maliev-<env>-orderstatus-service-config` entries that exist are empty JSON objects.
- `maliev-<env>-quotationrequest-service-config` entries contain QuotationRequest connection-string and UploadService keys, but the `Maliev.QuotationRequestService` repo and matching `3-apps/maliev-quotationrequest-service` app overlay are absent. Treat these as legacy retained payloads pending a retention/deletion decision, not as reusable QuotationService config.

### Expected Non-App References

- `cloudflare-api-token`
- `maliev-dev-pg-credentials`
- `maliev-dev-shared-config`
- `maliev-staging-shared-config`
- `maliev-prod-shared-config`

## Disabled Environment Secret References

The following GitOps `ExternalSecret` remote refs are present in staging/prod environment `secrets.yaml` files but are not rendered by the current environment kustomizations:

- `maliev-staging-pg-app-password`
- `maliev-staging-pg-superuser-password`
- `maliev-prod-pg-app-password`
- `maliev-prod-pg-superuser-password`

Create these Secret Manager entries with confirmed database credentials before uncommenting `secrets.yaml`, database, Redis, RabbitMQ, shared secrets, or common app resources in staging or production.

## Required Follow-Up

- Populate confirmed DB connection-string keys for every missing service secret listed above.
- Create or confirm the missing development databases before adding development connection strings for accounting, commerce, facility, IAM, registry, and search.
- Create or confirm staging/prod Postgres credential secrets before enabling their environment `secrets.yaml` resources.
- Create staging/prod DeliveryService secrets only after real staging/prod SHIPPOP or GoShip credentials and Delivery DB connection strings are confirmed.
- Decide whether staging/prod shared configs should include Redis/RabbitMQ/CORS keys, matching the development shared config shape.
- Decide whether missing service configs should be created or whether the corresponding GitOps app overlays are ahead of currently deployed services.
- Decide whether unreferenced service config secrets belong to removed services, disabled apps, or renamed services.

## Verification Commands Used

```powershell
gcloud secrets list --project maliev-website --format='value(name)'

B:\maliev\.agents\skills\maliev-secret-manager-audit\scripts\audit-secret-refs.ps1 `
  -GitOpsRoot B:\maliev\maliev-gitops `
  -Project maliev-website

B:\maliev\.agents\skills\maliev-secret-manager-audit\scripts\audit-secret-refs.ps1 `
  -GitOpsRoot B:\maliev\maliev-gitops `
  -Project maliev-website `
  -Json

Get-ChildItem -Path maliev-gitops\3-apps -Filter service-secrets-patch.yaml -Recurse |
  ForEach-Object {
    Select-String -Path $_.FullName -Pattern 'key:\s*(\S+)' |
      ForEach-Object { $_.Matches[0].Groups[1].Value }
  } | Sort-Object -Unique

kubectl kustomize 3-apps\maliev-delivery-service\overlays\development
kubectl kustomize 3-apps\maliev-delivery-service\overlays\staging
kubectl kustomize 3-apps\maliev-delivery-service\overlays\production
kubectl kustomize 3-apps\maliev-chatbot-service\overlays\development
kubectl kustomize 3-apps\maliev-chatbot-service\overlays\staging
kubectl kustomize 3-apps\maliev-chatbot-service\overlays\production
kubectl kustomize 2-environments\2-staging
kubectl kustomize 2-environments\3-production
kubectl kustomize 2-environments\0-live-production
kubectl get applications -n argocd -o custom-columns=NAME:.metadata.name,SYNC:.status.sync.status,HEALTH:.status.health.status,PATH:.spec.source.path --no-headers

Select-String over each missing service's `Program.cs`, options classes, and appsettings files for:
`AddPostgresDbContext`, `GetConnectionString`, `Configure<TOptions>`, `GetSection`, `AddHttpClient`, and environment-specific provider sections.
```
