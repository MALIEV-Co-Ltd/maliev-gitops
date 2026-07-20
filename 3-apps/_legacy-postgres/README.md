# Legacy PostgreSQL GitOps foundation

This package runs the temporary legacy data plane as one CloudNativePG cluster named
`legacy-postgres-main` in the dedicated `maliev-legacy` namespace. It does not change
or reuse the new platform's `maliev-dev`, `maliev-staging`, or `maliev-prod`
database resources.

Application traffic uses the CloudNativePG-managed PgBouncer service
`legacy-postgres-pooler-rw.maliev-legacy.svc:5432`. The pooler is deliberately a
single, resource-bounded instance for the temporary legacy runtime and uses
transaction pooling. Migration, bootstrap, backup, and administrative operations
continue to use the direct CloudNativePG services; only application connection
strings should target PgBouncer after the owner-approved cutover. The pooler name
is intentionally distinct from CloudNativePG's generated
`legacy-postgres-main-rw` service.

## Topology and tradeoff

The legacy applications share one physical PostgreSQL cluster while retaining a
separate logical database, owner role, and Kubernetes credential Secret per source
database. This minimizes CPU, memory, storage, operator, and backup overhead while
the replacement services are built. Two instances provide primary failover within
the current zone, and
CloudNativePG owns the disruption budget so its policy remains consistent with the
cluster topology. This is not multi-zone high availability; a zone outage still
affects both instances. The deliberate tradeoff is a shared maintenance
and failure blast radius: logical credentials prevent normal cross-database access,
but they do not provide physical fault isolation. This is temporary migration
infrastructure, not the target architecture.

`Log` is archive-only and is not provisioned as an active database.
`MachineLearningData` is excluded because deterministic pricing replaced the
prediction service. The source backup remains
`gs://maliev.com/database/full/2026-07-14/`; restoring it is a separately validated
migration operation and is not triggered automatically by these manifests.

## Active ownership inventory (21)

| Database | Owner role | Ownership |
| --- | --- | --- |
| Country | legacy_country_owner | Legacy service owning the existing Country schema |
| Currency | legacy_currency_owner | Legacy service owning the existing Currency schema |
| Customer | legacy_customer_owner | Legacy service owning the existing Customer schema |
| CustomerIdentity | legacy_customer_identity_owner | Legacy service owning the existing CustomerIdentity schema |
| DataProtectionKeys | legacy_data_protection_keys_owner | Legacy service owning the existing DataProtectionKeys schema |
| DataProtectionKeysEmployee | legacy_data_protection_keys_employee_owner | Legacy service owning the existing DataProtectionKeysEmployee schema |
| Employee | legacy_employee_owner | Legacy service owning the existing Employee schema |
| EmployeeIdentity | legacy_employee_identity_owner | Legacy service owning the existing EmployeeIdentity schema |
| Invoice | legacy_invoice_owner | Legacy service owning the existing Invoice schema |
| JobOffers | legacy_job_offers_owner | Legacy service owning the existing JobOffers schema |
| Material | legacy_material_owner | Legacy service owning the existing Material schema |
| Message | legacy_message_owner | Legacy service owning the existing Message schema |
| Order | legacy_order_owner | Legacy service owning the existing Order schema |
| OrderStatus | legacy_order_status_owner | Legacy service owning the existing OrderStatus schema |
| Payment | legacy_payment_owner | Legacy service owning the existing Payment schema |
| PurchaseOrder | legacy_purchase_order_owner | Legacy service owning the existing PurchaseOrder schema |
| Quotation | legacy_quotation_owner | Legacy service owning the existing Quotation schema |
| QuotationRequest | legacy_quotation_request_owner | Legacy service owning the existing QuotationRequest schema |
| Receipt | legacy_receipt_owner | Legacy service owning the existing Receipt schema |
| Supplier | legacy_supplier_owner | Legacy service owning the existing Supplier schema |
| Upload | legacy_upload_owner | Legacy service owning the existing Upload schema |

## Backup design

CloudNativePG 1.28 remains installed once in `cnpg-system`. The Barman Cloud CNPG-I
plugin v0.13.0 is installed beside it from the immutable release commit
`1cd26c92867bd27a8cc14beab8e455cf3b64cb10`. The official release manifest is
vendored locally and matches published asset digest
`sha256:d2e71e7b06822448f1a421f05781846cfdb9cc621e7ef32eef5e20c5133213b0`;
its multi-architecture image is pinned
to `sha256:71589dbac582333442812b07b31f7ea4d00324a8358aac7ca507dabf9f4b6c96`.
The cluster uses the plugin as its WAL archiver and schedules a daily plugin base
backup at 02:00 Asia/Bangkok (19:00 UTC). Backups and continuous WAL archives use
`gs://maliev.com/database/legacy-postgres/main/` with 14-day retention.

The deprecated native `Cluster.spec.backup.barmanObjectStore` API is intentionally
absent. GCS access uses keyless GKE Workload Identity.

The vendored upstream bundle labels the public `SIDECAR_IMAGE` value as a native
Kubernetes Secret. This repository represents that non-sensitive image metadata as
a ConfigMap instead and updates the Deployment reference accordingly. Because the
plugin consumes the value as a container image, the ConfigMap stores the decoded
literal image reference (not Secret-style base64) while complying with the
repository-wide ExternalSecret policy.

The initial `Country` database and `legacy_country_owner` role are created by
`bootstrap.initdb` from the same basic-auth Secret used by declarative role
management. The matching `Database/Country` resource then reconciles the existing
database with `ALTER DATABASE`, which CloudNativePG supports; the other 20 databases
are created declaratively after bootstrap.

## Required before merge

The `maliev-legacy` Argo Application is deliberately manual-sync. A July 14, 2026
capacity sample found all five single-zone nodes at roughly 77% to 110% memory use;
the two PostgreSQL pods request 512Mi each and cannot be assumed safely schedulable.
Before the first sync, use both `kubectl top nodes` and node allocated-request data
to prove that two distinct schedulable nodes each retain at least 1Gi of memory
headroom after existing workloads and that the existing cluster can also absorb
the pooler's 20m CPU/32Mi memory request. If that gate fails, reclaim existing
capacity and do not sync the Application; this migration does not authorize a new
node pool or any paid infrastructure. Re-check because the later cluster API reads
timed out and the snapshot may have changed.

Create the GCP service account
`legacy-postgres-main@maliev-website.iam.gserviceaccount.com`, then:

1. Grant it object create/read/list/delete access only to the `maliev.com` bucket,
   preferably with an IAM condition limited to the
   `database/legacy-postgres/main/` object prefix. `roles/storage.objectAdmin`
   at bucket scope is the simplest role that supports backup retention deletion.
2. Grant `roles/iam.workloadIdentityUser` on that GSA to
   `serviceAccount:maliev-website.svc.id.goog[maliev-legacy/legacy-postgres-main]`.
3. Verify External Secrets Operator can read the single GSM secret
   `maliev-legacy-secrets`.
4. Populate every property listed below. Do not commit their values.
5. Verify cert-manager and CloudNativePG 1.28 are healthy before enabling the
   Barman plugin Argo application.
6. Confirm the target GCS prefix is empty before the first cluster starts, or
   explicitly follow the CNPG recovery procedure for an existing archive.

## Required `maliev-legacy-secrets` properties

`legacy-postgres-superuser-username` must be exactly `postgres`; CloudNativePG
requires that username for `spec.superuserSecret`. Generate a unique high-entropy
value for every password property.

- `legacy-postgres-superuser-username`
- `legacy-postgres-superuser-password`
- `legacy-postgres-country-username`
- `legacy-postgres-country-password`
- `legacy-postgres-currency-username`
- `legacy-postgres-currency-password`
- `legacy-postgres-customer-username`
- `legacy-postgres-customer-password`
- `legacy-postgres-customer-identity-username`
- `legacy-postgres-customer-identity-password`
- `legacy-postgres-data-protection-keys-username`
- `legacy-postgres-data-protection-keys-password`
- `legacy-postgres-data-protection-keys-employee-username`
- `legacy-postgres-data-protection-keys-employee-password`
- `legacy-postgres-employee-username`
- `legacy-postgres-employee-password`
- `legacy-postgres-employee-identity-username`
- `legacy-postgres-employee-identity-password`
- `legacy-postgres-invoice-username`
- `legacy-postgres-invoice-password`
- `legacy-postgres-job-offers-username`
- `legacy-postgres-job-offers-password`
- `legacy-postgres-material-username`
- `legacy-postgres-material-password`
- `legacy-postgres-message-username`
- `legacy-postgres-message-password`
- `legacy-postgres-order-username`
- `legacy-postgres-order-password`
- `legacy-postgres-order-status-username`
- `legacy-postgres-order-status-password`
- `legacy-postgres-payment-username`
- `legacy-postgres-payment-password`
- `legacy-postgres-purchase-order-username`
- `legacy-postgres-purchase-order-password`
- `legacy-postgres-quotation-username`
- `legacy-postgres-quotation-password`
- `legacy-postgres-quotation-request-username`
- `legacy-postgres-quotation-request-password`
- `legacy-postgres-receipt-username`
- `legacy-postgres-receipt-password`
- `legacy-postgres-supplier-username`
- `legacy-postgres-supplier-password`
- `legacy-postgres-upload-username`
- `legacy-postgres-upload-password`

Each application property pair becomes one
`kubernetes.io/basic-auth` Secret in `maliev-legacy`. The username must exactly
match the corresponding owner role in the inventory.

## Argo CD ownership

`maliev-legacy` is reconciled by the `maliev-legacy` Application and AppProject.
The project admits only this repository and the `maliev-legacy` namespace. The
plugin is cluster infrastructure reconciled separately into `cnpg-system`; it does
not install another CloudNativePG operator.
