from __future__ import annotations

import subprocess
import unittest
from pathlib import Path

import yaml


REPO_ROOT = Path(__file__).resolve().parents[1]
ACTIVE_ENVIRONMENT = "2-environments/4-legacy/kustomization.yaml"


def render(path: str) -> list[dict]:
    result = subprocess.run(
        ["kubectl", "kustomize", str(REPO_ROOT / path)],
        cwd=REPO_ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    return [document for document in yaml.safe_load_all(result.stdout) if document]


def one(documents: list[dict], kind: str, name: str) -> dict:
    matches = [
        document
        for document in documents
        if document.get("kind") == kind
        and document.get("metadata", {}).get("name") == name
    ]
    if len(matches) != 1:
        raise AssertionError(f"Expected one {kind}/{name}, found {len(matches)}")
    return matches[0]


class LegacyRuntimeProjectionTests(unittest.TestCase):
    def test_projections_are_dormant_and_namespace_isolated(self) -> None:
        active = (REPO_ROOT / ACTIVE_ENVIRONMENT).read_text(encoding="utf-8")
        self.assertNotIn("_legacy-cutover", active)
        for path in (
            "3-apps/_legacy-web/base",
            "3-apps/_legacy-file-service/base",
            "3-apps/_legacy-accounting-service/base",
            "3-apps/_legacy-notification-service/base",
        ):
            documents = render(path)
            self.assertTrue(documents)
            self.assertTrue(
                all(
                    document["metadata"].get("namespace") in (None, "maliev-legacy")
                    for document in documents
                )
            )

    def test_web_projection_has_runtime_and_data_protection_contract(self) -> None:
        documents = render("3-apps/_legacy-web/base")
        external = one(documents, "ExternalSecret", "legacy-maliev-web-runtime")
        properties = {item["remoteRef"]["property"] for item in external["spec"]["data"]}
        self.assertEqual({item["remoteRef"]["key"] for item in external["spec"]["data"]}, {"maliev-legacy-secrets"})
        self.assertTrue(
            {
                "legacy-web-data-protection-certificate-pfx-base64",
                "legacy-web-data-protection-certificate-password",
                "legacy-web-service-client-secret",
                "legacy-web-google-maps-embed-api-key",
                "legacy-web-recaptcha-site-key",
                "legacy-web-recaptcha-project-id",
            }.issubset(properties)
        )
        self.assertEqual(
            set(external["spec"]["target"]["template"]["data"]),
            {
                "ConnectionStrings__redis",
                "DataProtection__CertificatePfxBase64",
                "DataProtection__CertificatePassword",
                "ServiceAuthentication__ClientId",
                "ServiceAuthentication__ClientSecret",
                "Recaptcha__SiteKey",
                "Recaptcha__ProjectId",
                "GoogleMaps__EmbedApiKey",
            },
        )

    def test_file_projection_keeps_upload_scanning_fail_closed_contract(self) -> None:
        documents = render("3-apps/_legacy-file-service/base")
        external = one(documents, "ExternalSecret", "legacy-maliev-file-runtime")
        properties = {item["remoteRef"]["property"] for item in external["spec"]["data"]}
        self.assertEqual({item["remoteRef"]["key"] for item in external["spec"]["data"]}, {"maliev-legacy-secrets"})
        self.assertTrue(
            {
                "legacy-postgres-upload-username",
                "legacy-postgres-upload-password",
                "legacy-jwt-public-key",
                "legacy-jwt-issuer",
                "legacy-jwt-audience",
            }.issubset(properties)
        )
        template = external["spec"]["target"]["template"]["data"]
        self.assertEqual(template["FileStorage__AllowedBuckets__0"], "maliev.com")
        self.assertEqual(template["FileStorage__AllowedBuckets__1"], "maliev-instant-quotations")
        self.assertEqual(template["FileStorage__AllowedBuckets__2"], "maliev-quotation-requests")
        self.assertEqual(template["FileStorage__QuarantinePrefix"], "_quarantine")
        self.assertEqual(template["FileStorage__SignedUrlHours"], "168")
        self.assertEqual(template["MalwareScanner__Host"], "legacy-clamav")
        self.assertEqual(template["MalwareScanner__Port"], "3310")
        self.assertIn("ConnectionStrings__FileDbContext", template)

    def test_accounting_projection_has_all_financial_databases_and_cache(self) -> None:
        documents = render("3-apps/_legacy-accounting-service/base")
        external = one(documents, "ExternalSecret", "legacy-maliev-accounting-runtime")
        properties = {item["remoteRef"]["property"] for item in external["spec"]["data"]}
        self.assertEqual({item["remoteRef"]["key"] for item in external["spec"]["data"]}, {"maliev-legacy-secrets"})
        self.assertTrue(
            {
                "legacy-postgres-payment-username",
                "legacy-postgres-payment-password",
                "legacy-postgres-invoice-username",
                "legacy-postgres-invoice-password",
                "legacy-postgres-receipt-username",
                "legacy-postgres-receipt-password",
                "legacy-redis-password",
                "legacy-jwt-public-key",
                "legacy-jwt-issuer",
                "legacy-jwt-audience",
                "legacy-accounting-service-client-secret",
            }.issubset(properties)
        )
        template = external["spec"]["target"]["template"]["data"]
        for key in (
            "ConnectionStrings__PaymentDbContext",
            "ConnectionStrings__InvoiceDbContext",
            "ConnectionStrings__ReceiptDbContext",
            "ConnectionStrings__redis",
            "ServiceAuthentication__ClientSecret",
        ):
            self.assertIn(key, template)

    def test_notification_projection_has_brevo_and_jwt_contract(self) -> None:
        documents = render("3-apps/_legacy-notification-service/base")
        external = one(documents, "ExternalSecret", "legacy-maliev-notification-service")
        self.assertEqual({item["remoteRef"]["key"] for item in external["spec"]["data"]}, {"maliev-legacy-secrets"})
        self.assertEqual(
            {item["remoteRef"]["property"] for item in external["spec"]["data"]},
            {
                "legacy-notification-brevo-api-key",
                "legacy-jwt-public-key",
                "legacy-jwt-issuer",
                "legacy-jwt-audience",
            },
        )

    def test_service_accounts_are_non_automounting_and_bound_to_expected_gsas(self) -> None:
        expected = {
            "3-apps/_legacy-web/base": ("legacy-maliev-web", "legacy-maliev-web@maliev-website.iam.gserviceaccount.com"),
            "3-apps/_legacy-file-service/base": ("legacy-maliev-file", "legacy-maliev-file@maliev-website.iam.gserviceaccount.com"),
            "3-apps/_legacy-accounting-service/base": ("legacy-maliev-accounting", "legacy-maliev-accounting@maliev-website.iam.gserviceaccount.com"),
            "3-apps/_legacy-notification-service/base": ("legacy-maliev-notification", "legacy-maliev-notification@maliev-website.iam.gserviceaccount.com"),
        }
        for path, (name, gsa) in expected.items():
            service_account = one(render(path), "ServiceAccount", name)
            self.assertFalse(service_account["automountServiceAccountToken"])
            self.assertEqual(service_account["metadata"]["annotations"]["iam.gke.io/gcp-service-account"], gsa)


if __name__ == "__main__":
    unittest.main()
