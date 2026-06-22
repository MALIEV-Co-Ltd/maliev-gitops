# SHIPPOP Staging/Production Secret Value Checklist - 2026-06-22

This checklist is the remaining value-gathering target for SHIPPOP deployment readiness.
It does not contain secret values.

Use it before activating DeliveryService, Web, QuoteEngine, or Intranet in staging or production.
Do not deploy to GKE, move ArgoCD Applications out of `_disabled_apps`, or enable staging/production environment resources until the required secrets below exist and pass the redacted checks.

## Current Audit Result

Latest redacted audit command:

```powershell
B:\maliev\.agents\skills\maliev-secret-manager-audit\scripts\audit-secret-refs.ps1 `
  -GitOpsRoot B:\maliev\maliev-gitops `
  -Project maliev-website `
  -Json
```

Observed result:

- Active app overlay config secrets missing in Google Secret Manager: `0`
- Disabled app overlay config secrets missing in Google Secret Manager: `22`
- SHIPPOP-critical disabled secrets missing:
  - `maliev-staging-delivery-service-config`
  - `maliev-prod-delivery-service-config`
  - `maliev-staging-quote-engine-config`
  - `maliev-prod-quote-engine-config`
- Existing but missing shipping endpoint keys in the checked payload:
  - `maliev-staging-web-config`
  - `maliev-prod-web-config`
  - `maliev-staging-intranet-config`
  - `maliev-prod-intranet-config`
- Disabled environment PostgreSQL credential refs missing:
  - `maliev-staging-pg-app-password`
  - `maliev-staging-pg-superuser-password`
  - `maliev-prod-pg-app-password`
  - `maliev-prod-pg-superuser-password`

## Known Safe Reuse

These values are not provider credentials and can be used as configuration constants once the corresponding service is deployed in the same namespace:

| Environment | Key | Value source |
| --- | --- | --- |
| Staging | `Services__DeliveryService__BaseUrl` | Kubernetes Service `maliev-delivery-service` on port `8080` in namespace `maliev-staging` |
| Production | `Services__DeliveryService__BaseUrl` | Kubernetes Service `maliev-delivery-service` on port `8080` in namespace `maliev-prod` |
| Staging/Production | `Web__BaseUrl` | Confirmed public Web base URL: `https://www.maliev.com` |
| Staging/Production | `QuoteEngine__BaseUrl` | Confirmed public QuoteEngine base URL: `https://make.maliev.com` |

Do not copy development database passwords, SHIPPOP API keys, or SHIPPOP bearer tokens into staging or production unless the business decision is explicitly to use the development SHIPPOP tenant in that environment.

## Staging Checklist

### `maliev-staging-delivery-service-config`

Status: missing in Google Secret Manager.

Required keys:

- `ConnectionStrings__DeliveryDbContext`
- `Shippop__DomesticBaseUrl`
- `Shippop__DomesticApiKey`
- `Shippop__DomesticEmail`
- `Shippop__InternationalBaseUrl`

Values to confirm before creation:

- Staging DeliveryService database host, database name, username, password, SSL mode, and connection-string policy.
- Whether staging should use SHIPPOP dev/test credentials or a dedicated staging-capable SHIPPOP account.
- SHIPPOP domestic base URL for staging. If using SHIPPOP dev, it must stay on the `.shippop.dev` host.
- SHIPPOP domestic API key for the selected staging account.
- SHIPPOP account email for the selected staging account.
- SHIPPOP international/public tracking base URL for the selected staging account.

Optional keys:

- `Shippop__InternationalBearerToken` only if authenticated SHIPPOP Inter shipment creation is enabled.
- `GoShip__BaseUrl`, `GoShip__AppId`, and `GoShip__Secret` only if GoShip fallback is enabled.

### `maliev-staging-quote-engine-config`

Status: missing in Google Secret Manager.

Required keys:

- `Web__BaseUrl`
- `QuoteEngine__BaseUrl`
- `Services__DeliveryService__BaseUrl`

Values to confirm before creation:

- Whether staging QuoteEngine should use the public `https://make.maliev.com` host or a staging host.
- Whether staging Web should use the public `https://www.maliev.com` host or a staging host.
- Staging in-cluster DeliveryService URL.

Optional keys:

- `GoogleMaps__BrowserApiKey` only after the staging browser key and allowed referrers are confirmed.

### `maliev-staging-web-config`

Status: exists in Google Secret Manager, but the redacted SHIPPOP-related key check found no shipping endpoint key.

Required shipping key before Web shipping activation:

- `Services__DeliveryService__BaseUrl`

Values to confirm before update:

- Staging in-cluster DeliveryService URL.
- Whether staging Web should also carry `QuoteEngine__BaseUrl` for the Make Studio handoff.

### `maliev-staging-intranet-config`

Status: exists in Google Secret Manager, but the redacted SHIPPOP-related key check found no shipping endpoint key.

Required shipping key before Intranet shipping activation:

- `Services__DeliveryService__BaseUrl`

Values to confirm before update:

- Staging in-cluster DeliveryService URL.
- Whether existing Intranet callback/base URL keys must be preserved when adding a new secret version.

### Staging PostgreSQL environment refs

Status: referenced by `2-environments/2-staging/secrets.yaml`, but missing in Google Secret Manager and not currently rendered by the staging kustomization.

Required Secret Manager entries:

- `maliev-staging-pg-app-password`
- `maliev-staging-pg-superuser-password`

Values to confirm before creation:

- Staging PostgreSQL app username and password.
- Staging PostgreSQL superuser username and password.
- Whether staging PostgreSQL is shared with dev, isolated in the same cluster, or isolated in a separate cluster.

## Production Checklist

### `maliev-prod-delivery-service-config`

Status: missing in Google Secret Manager.

Required keys:

- `ConnectionStrings__DeliveryDbContext`
- `Shippop__DomesticBaseUrl`
- `Shippop__DomesticApiKey`
- `Shippop__DomesticEmail`
- `Shippop__InternationalBaseUrl`

Values to confirm before creation:

- Production DeliveryService database host, database name, username, password, SSL mode, and connection-string policy.
- Production SHIPPOP account approval status.
- Production SHIPPOP domestic base URL. This must not be the development host unless explicitly approved for a non-production dry run.
- Production SHIPPOP domestic API key.
- Production SHIPPOP account email.
- Production SHIPPOP international/public tracking base URL.

Optional keys:

- `Shippop__InternationalBearerToken` only if authenticated SHIPPOP Inter shipment creation is enabled.
- `GoShip__BaseUrl`, `GoShip__AppId`, and `GoShip__Secret` only if GoShip fallback is enabled.

### `maliev-prod-quote-engine-config`

Status: missing in Google Secret Manager.

Required keys:

- `Web__BaseUrl`
- `QuoteEngine__BaseUrl`
- `Services__DeliveryService__BaseUrl`

Values to confirm before creation:

- Production Web base URL.
- Production QuoteEngine base URL.
- Production in-cluster DeliveryService URL.

Optional keys:

- `GoogleMaps__BrowserApiKey` only after the production browser key and allowed referrers are confirmed.

### `maliev-prod-web-config`

Status: exists in Google Secret Manager, but the redacted SHIPPOP-related key check found no shipping endpoint key.

Required shipping key before Web shipping activation:

- `Services__DeliveryService__BaseUrl`

Values to confirm before update:

- Production in-cluster DeliveryService URL.
- Whether Web also needs `QuoteEngine__BaseUrl` preserved or added for customer handoff flows.

### `maliev-prod-intranet-config`

Status: exists in Google Secret Manager, but the redacted SHIPPOP-related key check found no shipping endpoint key.

Required shipping key before Intranet shipping activation:

- `Services__DeliveryService__BaseUrl`

Values to confirm before update:

- Production in-cluster DeliveryService URL.
- Whether existing Intranet callback/base URL keys must be preserved when adding a new secret version.

### Production PostgreSQL environment refs

Status: referenced by `2-environments/3-production/secrets.yaml`, but missing in Google Secret Manager and not currently rendered by the production kustomization.

Required Secret Manager entries:

- `maliev-prod-pg-app-password`
- `maliev-prod-pg-superuser-password`

Values to confirm before creation:

- Production PostgreSQL app username and password.
- Production PostgreSQL superuser username and password.
- Whether production PostgreSQL is isolated from staging and dev.

## Shared Config Decision

Existing staging/production shared configs currently contain JWT keys only.
Before app activation, decide whether to add the same shared runtime keys used in development:

- `ConnectionStrings__rabbitmq`
- `ConnectionStrings__redis`
- `CORS__AllowedOrigins`
- `RabbitMq__Username`
- `RabbitMq__Password`

Do not add these without confirming the staging/production Redis and RabbitMQ deployment model.

## Redacted Validation Commands

List exact Secret Manager names:

```powershell
$names = @(
  'maliev-staging-delivery-service-config',
  'maliev-prod-delivery-service-config',
  'maliev-staging-web-config',
  'maliev-prod-web-config',
  'maliev-staging-quote-engine-config',
  'maliev-prod-quote-engine-config',
  'maliev-staging-intranet-config',
  'maliev-prod-intranet-config',
  'maliev-staging-pg-app-password',
  'maliev-staging-pg-superuser-password',
  'maliev-prod-pg-app-password',
  'maliev-prod-pg-superuser-password'
)
$existing = gcloud secrets list --project maliev-website --format='value(name)' |
  ForEach-Object { ($_ -split '/')[-1] }
$names | ForEach-Object {
  if ($existing -contains $_) { "EXISTS $_" } else { "MISSING $_" }
}
```

Inspect only key names and value types for a JSON payload:

```powershell
$secret = '<secret-name>'
$payload = gcloud secrets versions access latest --project maliev-website --secret $secret
$obj = $payload | ConvertFrom-Json -AsHashtable
$obj.Keys | Sort-Object | ForEach-Object {
  $value = $obj[$_]
  $kind = if ($null -eq $value) {
    'null'
  } elseif ($value -is [string]) {
    if ($value.Length -eq 0) { 'empty-string' } else { "string(len=$($value.Length))" }
  } else {
    $value.GetType().Name
  }
  "$_ = $kind"
}
```

Rerun the full name audit:

```powershell
B:\maliev\.agents\skills\maliev-secret-manager-audit\scripts\audit-secret-refs.ps1 `
  -GitOpsRoot B:\maliev\maliev-gitops `
  -Project maliev-website
```

Render the relevant disabled overlays before activation:

```powershell
kubectl kustomize B:\maliev\maliev-gitops\3-apps\maliev-delivery-service\overlays\staging
kubectl kustomize B:\maliev\maliev-gitops\3-apps\maliev-delivery-service\overlays\production
kubectl kustomize B:\maliev\maliev-gitops\3-apps\maliev-web\overlays\staging
kubectl kustomize B:\maliev\maliev-gitops\3-apps\maliev-web\overlays\production
kubectl kustomize B:\maliev\maliev-gitops\3-apps\maliev-quote-engine\overlays\staging
kubectl kustomize B:\maliev\maliev-gitops\3-apps\maliev-quote-engine\overlays\production
kubectl kustomize B:\maliev\maliev-gitops\3-apps\maliev-intranet\overlays\staging
kubectl kustomize B:\maliev\maliev-gitops\3-apps\maliev-intranet\overlays\production
```

## Completion Criteria

This checklist is complete when:

- The two missing DeliveryService service-config secrets exist with the required keys.
- The two missing QuoteEngine service-config secrets exist with the required keys.
- Staging/prod Web and Intranet configs contain `Services__DeliveryService__BaseUrl`.
- The four staging/prod PostgreSQL Secret Manager entries exist before their environment `secrets.yaml` resources are enabled.
- Redacted key inspection shows required key presence and non-empty values except for explicitly optional keys.
- No production deployment has been triggered as part of this checklist work.
