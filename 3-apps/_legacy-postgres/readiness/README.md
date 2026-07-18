# Legacy PostgreSQL migration readiness

This directory is deliberately dormant. Nothing below it is referenced by
`2-environments/4-legacy`, so merging it cannot create a disk, pod, service, node pool,
Cloud SQL instance, or cluster mutation.

`migration-readiness-contract.json` anchors the redacted receipts already committed at
`MALIEV-Co-Ltd/maliev-web@eb8ed86672bd9afccc6560b547b734d0fcd7363b` and pins each receipt's
raw SHA-256 digest. The executable verifier accepts:

- `legacy-database-restore-2026-07-14.json`: 23 backups, 510,709,760 bytes, 23 clean DBCC checks;
- `legacy-identity-copy-2026-07-15.json`: CustomerIdentity 3,048 rows and EmployeeIdentity 4 rows;
- `legacy-postgresql-copy-all-nonidentity-2026-07-16.json`: the other 19 active databases.

`MachineLearningData` is always excluded and `Log` remains archive-only. Passing those historical
receipts proves only the disposable copy baseline. It never authorizes cutover.

From a checkout containing both repositories, run:

```powershell
python .\scripts\legacy_data_readiness.py `
  --restore-evidence ..\maliev-web\docs\migration\evidence\legacy-database-restore-2026-07-14.json `
  --identity-evidence ..\maliev-web\docs\migration\evidence\legacy-identity-copy-2026-07-15.json `
  --nonidentity-evidence ..\maliev-web\docs\migration\evidence\legacy-postgresql-copy-all-nonidentity-2026-07-16.json
```

Adding `--require-cutover` must fail until a separate live receipt proves every required gate and
records explicit owner approval plus the source write freeze. The verifier never connects to either
database and never calls `kubectl`, Argo CD, Google Cloud, or the Kubernetes API.

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
