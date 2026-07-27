# Legacy Intranet secret projection

This overlay is intentionally dormant. It supplies the same
`legacy-maliev-intranet-runtime` name consumed by the legacy compatibility and BFF
deployments, but it is not included by `2-environments/4-legacy/kustomization.yaml`.

The projection is property-scoped from `maliev-legacy-secrets` and keeps Redis/Data
Protection, JWT verification, the BFF service credential, Google OAuth client ID, and
the separately restricted browser Maps key together without mounting the full JSON
bundle. Activate only after the Intranet KSA/GSA, downstream services, capacity, and
owner parity gates pass.
