# Legacy MALIEV Notification Service

This dormant overlay prepares the internal-only .NET 10 legacy notification service without adding it to
`2-environments/4-legacy`. The manual-sync Argo application therefore cannot render or deploy it until the
owner approves the completed Aspire review and a separate change explicitly enables the overlay.

The service owns no database and does not use Redis. Runtime secrets come only from the consolidated
`maliev-legacy-secrets` Google Secret Manager document: the Brevo API key plus the shared legacy JWT public
verification contract. Sender addresses and display names remain non-secret application configuration.

The NetworkPolicy permits same-namespace HTTP callers, cluster DNS, and outbound HTTPS for the Brevo API.
There is no ingress, PostgreSQL, Redis, GCS, or Kubernetes API access.

The dormant overlay deliberately renders the non-runnable `not-published` image tag. A later owner-approved
promotion must replace it with the exact published commit tag while enabling the overlay in a separate change.
