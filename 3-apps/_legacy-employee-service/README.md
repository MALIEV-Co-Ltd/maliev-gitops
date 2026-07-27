# Legacy EmployeeService runtime projection

This is a dormant, namespace-scoped projection for
`Legacy.Maliev.EmployeeService`. It is deliberately not referenced by
`2-environments/4-legacy/kustomization.yaml`; adding it to the active overlay
requires the EmployeeService image, Workload Identity, database parity,
capacity, consumer tests, and owner cutover gates.

The projection reads only `maliev-legacy-secrets` and produces the exact
`legacy-maliev-employee-runtime` bindings documented by the service:

- `ConnectionStrings__EmployeeDbContext`
- `ConnectionStrings__redis`
- `Jwt__PublicKey`
- `Jwt__Issuer`
- `Jwt__Audience`

No identity credentials, refresh tokens, signing keys, or service-account key
files are projected. GCS signature objects remain ADC/Workload Identity data.
