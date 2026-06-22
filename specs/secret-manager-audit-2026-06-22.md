# Secret Manager Audit - 2026-06-22

This audit compares `maliev-gitops` `ExternalSecret` references with Google Secret Manager in project `maliev-website`.

No secret values are stored in this file. Key presence and required follow-up only.

## Changes Applied

- Created `maliev-dev-delivery-service-config` in Google Secret Manager with SHIPPOP dev configuration keys only.
- Corrected DeliveryService production overlay from `maliev-production-delivery-service-config` to `maliev-prod-delivery-service-config`.
- Corrected chatbot overlays to consume existing LINE chatbot secrets:
  - `maliev-dev-line-chatbot-service-config`
  - `maliev-staging-line-chatbot-service-config`
  - `maliev-prod-line-chatbot-service-config`

## Verified Existing DeliveryService Dev Secret Keys

`maliev-dev-delivery-service-config` currently contains:

- `Shippop__DomesticApiKey`
- `Shippop__DomesticBaseUrl`
- `Shippop__DomesticEmail`
- `Shippop__InternationalBaseUrl`
- `Shippop__InternationalBearerToken`

It still does not contain `ConnectionStrings__DeliveryDbContext`.

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

Current development PostgreSQL databases observed from the live `maliev-dev` Postgres cluster:

- `app_db`
- `auth_app_db`
- `career_app_db`
- `contact_app_db`
- `contact_app_test_db`
- `country_app_db`
- `currency_app_db`
- `customer_app_db`
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

The live development cluster does not currently show databases for the missing service config families listed below, including accounting, commerce, delivery, facility, IAM, registry, and search. Do not create connection strings for those services until the target databases and credentials are created or otherwise confirmed.

## Confirmed Required Service-Specific Keys

These keys were derived from each service's startup/configuration code and current appsettings shape. Values are intentionally not recorded here.

| Service secret family | Confirmed service-specific keys |
| --- | --- |
| `maliev-<env>-accounting-service-config` | `ConnectionStrings__AccountingDbContext` |
| `maliev-<env>-commerce-service-config` | `ConnectionStrings__CommerceDbContext` |
| `maliev-<env>-contact-service-config` | `ConnectionStrings__ContactDbContext` |
| `maliev-<env>-delivery-service-config` | `ConnectionStrings__DeliveryDbContext`, `Shippop__DomesticBaseUrl`, `Shippop__DomesticApiKey`, `Shippop__DomesticEmail`, `Shippop__InternationalBaseUrl`, `Shippop__InternationalBearerToken`, `GoShip__BaseUrl`, `GoShip__AppId`, `GoShip__Secret` |
| `maliev-<env>-facility-service-config` | `ConnectionStrings__FacilityDbContext` |
| `maliev-<env>-iam-service-config` | `ConnectionStrings__IamDbContext` |
| `maliev-<env>-quote-engine-config` | `Web__BaseUrl`, `QuoteEngine__BaseUrl`, `GoogleMaps__BrowserApiKey` if Google Maps is enabled for that environment; service endpoint overrides may also be needed when Aspire service discovery is not available |
| `maliev-<env>-registry-service-config` | `ConnectionStrings__RegistryDbContext`, optional provider keys `BDEX__ConsumerKey` and `BDEX__ConsumerSecret` if BDEX is enabled |
| `maliev-<env>-search-service-config` | `ConnectionStrings__SearchDbContext` |

Notes:

- Existing `maliev-dev-contact-service-config` contains only `ConnectionStrings__ContactDbContext`, which matches the current minimum service-specific requirement.
- Existing `maliev-dev-order-service-config` shows the established pattern of service-specific DB connection strings plus external service endpoint overrides.
- `ConnectionStrings__IamDbContext` uses the casing from `Maliev.IAMService.Api/Program.cs`.
- Do not infer DB names, usernames, or passwords from neighboring services. Create or update these Secret Manager entries only with confirmed environment-specific values.

## Missing GitOps References In Google Secret Manager

These `3-apps/*/overlays/*/service-secrets-patch.yaml` references do not currently exist in Google Secret Manager:

### Development

- `maliev-dev-accounting-service-config`
- `maliev-dev-commerce-service-config`
- `maliev-dev-facility-service-config`
- `maliev-dev-iam-service-config`
- `maliev-dev-quote-engine-config`
- `maliev-dev-registry-service-config`
- `maliev-dev-search-service-config`

### Staging

- `maliev-staging-accounting-service-config`
- `maliev-staging-commerce-service-config`
- `maliev-staging-contact-service-config`
- `maliev-staging-delivery-service-config`
- `maliev-staging-facility-service-config`
- `maliev-staging-iam-service-config`
- `maliev-staging-quote-engine-config`
- `maliev-staging-registry-service-config`
- `maliev-staging-search-service-config`

### Production

- `maliev-prod-accounting-service-config`
- `maliev-prod-commerce-service-config`
- `maliev-prod-contact-service-config`
- `maliev-prod-delivery-service-config`
- `maliev-prod-facility-service-config`
- `maliev-prod-iam-service-config`
- `maliev-prod-quote-engine-config`
- `maliev-prod-registry-service-config`
- `maliev-prod-search-service-config`

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

### Expected Non-App References

- `cloudflare-api-token`
- `maliev-dev-pg-credentials`
- `maliev-dev-shared-config`
- `maliev-staging-shared-config`
- `maliev-prod-shared-config`

## Required Follow-Up

- Populate confirmed DB connection-string keys for every missing service secret listed above.
- Populate `ConnectionStrings__DeliveryDbContext` in `maliev-dev-delivery-service-config`.
- Create or confirm the missing development databases before adding development connection strings for accounting, commerce, delivery, facility, IAM, registry, and search.
- Create or confirm staging/prod Postgres credential secrets before enabling their environment `secrets.yaml` resources.
- Create staging/prod DeliveryService secrets only after real staging/prod SHIPPOP or GoShip credentials and Delivery DB connection strings are confirmed.
- Decide whether staging/prod shared configs should include Redis/RabbitMQ/CORS keys, matching the development shared config shape.
- Decide whether missing service configs should be created or whether the corresponding GitOps app overlays are ahead of currently deployed services.
- Decide whether unreferenced service config secrets belong to removed services, disabled apps, or renamed services.

## Verification Commands Used

```powershell
gcloud secrets list --project maliev-website --format='value(name)'

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

Select-String over each missing service's `Program.cs`, options classes, and appsettings files for:
`AddPostgresDbContext`, `GetConnectionString`, `Configure<TOptions>`, `GetSection`, `AddHttpClient`, and environment-specific provider sections.
```
