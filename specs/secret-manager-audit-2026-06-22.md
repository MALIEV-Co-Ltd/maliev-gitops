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

- Populate `ConnectionStrings__DeliveryDbContext` for:
  - `maliev-dev-delivery-service-config`
  - `maliev-staging-delivery-service-config`
  - `maliev-prod-delivery-service-config`
- Create staging/prod DeliveryService secrets only after real staging/prod SHIPPOP credentials and Delivery DB connection strings are confirmed.
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
```
