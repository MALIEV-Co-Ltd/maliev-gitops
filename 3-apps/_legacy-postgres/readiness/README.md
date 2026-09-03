# Legacy PostgreSQL migration readiness

This directory is deliberately dormant. Nothing below it is referenced by
`2-environments/4-legacy`, so merging it cannot create a disk, pod, service, node pool,
Cloud SQL instance, or cluster mutation.

`migration-readiness-contract.json` anchors the redacted receipts already committed at
`MALIEV-Co-Ltd/maliev-web@eb8ed86672bd9afccc6560b547b734d0fcd7363b` and records the latest
read-only source audit at `MALIEV-Co-Ltd/maliev-web@edf451e367ce774d63a74778731bb3c20daf1063`.
It pins each receipt's
raw SHA-256 digest. The executable verifier accepts:

- `legacy-database-restore-2026-07-14.json`: 23 backups, 510,709,760 bytes, 23 clean DBCC checks;
- `legacy-identity-copy-2026-07-15.json`: CustomerIdentity 3,048 rows and EmployeeIdentity 4 rows;
- `legacy-postgresql-copy-all-nonidentity-2026-07-16.json`: the other 19 active databases.

`MachineLearningData` is always excluded and `Log` remains archive-only. Passing those historical
receipts proves only the disposable copy baseline. It never authorizes cutover.

`legacy-service-database-contract.json` is the companion service-boundary ledger. It accounts for
all 21 CNPG databases, their owner roles, every database-consuming Legacy service and connection
key, the explicitly retained source-only databases, and the active/deferred/planned GitOps
resources. A deferred resource has a checked-in dormant projection; a planned resource is named
for audit purposes but has no deployment directory yet. The
`tests.test_legacy_service_database_contract` suite checks this ledger against the CNPG manifests,
the active Country pooler secret, and the locally available Legacy repositories without reading
secret values or connecting to production.

`legacy-secret-contract.json` also records the value-free username/password property for every
active CNPG database and the deferred Auth refresh-session store. The secret-contract tests require
these bindings to cover the database ledger exactly and keep the deferred binding out of the active
environment until its database and recovery gates are approved.

`legacy-runtime-inventory.json` is the deployment-surface ledger for all Legacy application
repositories. It records each service's active/deferred/planned GitOps resource and the health
prefix implemented by its migrated .NET host. `tests.test_legacy_runtime_inventory` compares the
ledger with the database/resource contract and the checked-in source while never applying a
manifest or contacting a cluster.

`current-parity-audit-2026-08-07.json` is a redacted, read-only observation of the current
reconciliation boundary. It deliberately records that the latest visible SQL Server backup is
2026-07-20 (not 2026-08-07), that the Auth Database resource is unapplied, and that no Legacy
application workloads are deployed. It also records that only the four identity databases have
`__EFMigrationsHistory`; the 17 domain databases do not, and no schema-baseline receipt files are
currently projected. `LEGACY_SKIP_MIGRATE=true` therefore remains required until each imported
domain schema has a source-backed receipt and a reviewed migration-history reconciliation. It is
an audit checkpoint, not a migration receipt and it cannot authorize cutover.

The same audit found that the live domain timestamp columns are `timestamp without time zone`,
while the imported service models had previously declared `timestamp with time zone`. The
canonical Legacy services now carry explicit UTC-preserving conversions and model mappings for
Accounting, Catalog, Career, Contact, Country, Customer, Employee, Order, Procurement, and
Quotation. Those migrations are local code evidence only: they have not been applied to the live
target because the migration runner remains skipped and the schema-history gate is still closed.
The `domain-timestamp-schema-activation` blocker therefore remains until an owner-approved,
row-preserving schema application and verification receipt exists.

From the GitOps checkout with the read-only source evidence checkout available, run:

```powershell
$sourceRoot = if ($env:MALIEV_SOURCE_ROOT) { $env:MALIEV_SOURCE_ROOT } else { 'R:\maliev-web' }
python .\scripts\legacy_data_readiness.py `
  --restore-evidence (Join-Path $sourceRoot 'docs\migration\evidence\legacy-database-restore-2026-07-14.json') `
  --identity-evidence (Join-Path $sourceRoot 'docs\migration\evidence\legacy-identity-copy-2026-07-15.json') `
  --nonidentity-evidence (Join-Path $sourceRoot 'docs\migration\evidence\legacy-postgresql-copy-all-nonidentity-2026-07-16.json')
```

Run the local contract tests with:

```powershell
python -m unittest tests.test_legacy_data_readiness tests.test_legacy_service_database_contract -v
```

Adding `--require-cutover` must fail until a separate live receipt proves every required gate and
records explicit owner approval plus the source write freeze. The verifier never connects to either
database and never calls `kubectl`, Argo CD, Google Cloud, or the Kubernetes API.

## Live parity receipt

`scripts/legacy_live_parity.py` validates the next migration evidence artifact:
an externally collected, value-free source/target receipt. The collector must
use a read-only SQL Server principal inside a snapshot transaction and record
only database/table inventories, row/null counts, canonical content hashes,
foreign-key orphan counts, identity sequence state, and schema fingerprints.
The target must be `maliev-legacy/legacy-postgres-main`. The validator has no
database or cluster access, rejects credential-shaped fields, and is not a
cutover authorization by itself.

```powershell
python scripts/legacy_live_parity.py --receipt live-parity-receipt.json
python -m unittest tests.test_legacy_live_parity -v
```

The existing `legacy_data_readiness.py --require-cutover` gate must still pass
with a separate complete live receipt, source write-freeze confirmation, and
owner approval before any service is promoted or any target writer is changed.

## CNPG recovery rehearsal

`recovery-rehearsal` renders a one-instance, resource-bounded cluster named
`legacy-postgres-recovery-rehearsal` in `maliev-legacy`. It reads the
`legacy-postgres-main` Barman archive through the existing Workload Identity and does not configure
a WAL writer, preventing the rehearsal from writing into the source archive.

The recovery manifest may be activated only in a separate owner-approved GitOps PR after all of the
following are true:

1. Existing-cluster capacity is re-measured and one 150m CPU/512Mi memory pod plus a 20Gi
   `standard-rwo` volume can fit without a new node pool.
2. `legacy-postgres-main` has a successful base backup and continuous WAL archive.
3. The GCS recovery window covers the selected target.
4. The active legacy source remains authoritative and unmodified.
5. The rehearsal PR adds only this path to a temporary manual-sync Argo application.

After recovery, reconcile database inventory, schema fingerprints, table row/null counts, stable
content hashes, foreign-key orphans, and identity sequence high-water marks. Delete the temporary
GitOps reference only after preserving the redacted drill receipt. Do not add this path to the active
legacy environment as part of this readiness change.

## Cutover and rollback contract

Cutover remains blocked until the verifier receives passing live evidence for capacity, CNPG
backup/WAL, a clean recovery drill, shadow reads, final freeze/sync reconciliation, a timed rollback
rehearsal, the complete Aspire owner review, and per-service approval. Promotion is service-by-service
through reviewed GitOps connection changes; no bulk routing switch is permitted.

Rollback is also service-by-service. Freeze the affected PostgreSQL writer, capture and reconcile the
target-only delta back into the retained SQL Server authority using the separately rehearsed tool,
verify hashes and counts, then revert only that service's GitOps connection change. If reverse-delta
evidence or owner approval is absent, remain on PostgreSQL and resolve forward; never route back while
discarding acknowledged writes.
