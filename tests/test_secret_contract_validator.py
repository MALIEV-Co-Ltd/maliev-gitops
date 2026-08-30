from __future__ import annotations

import base64
import unittest

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa

from scripts.validate_legacy_secret_contract import validate_value_shapes


class SecretContractValueValidationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        cls.private_pem = cls.private_key.private_bytes(
            serialization.Encoding.PEM,
            serialization.PrivateFormat.PKCS8,
            serialization.NoEncryption(),
        ).decode("ascii")
        cls.public_pem = cls.private_key.public_key().public_bytes(
            serialization.Encoding.PEM,
            serialization.PublicFormat.SubjectPublicKeyInfo,
        ).decode("ascii")
        other_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        cls.other_public_pem = other_key.public_key().public_bytes(
            serialization.Encoding.PEM,
            serialization.PublicFormat.SubjectPublicKeyInfo,
        ).decode("ascii")

    def valid_payload(self) -> dict[str, str]:
        return {
            "legacy-jwt-private-key": self.private_pem,
            "legacy-jwt-public-key": self.public_pem,
            "legacy-jwt-key-id": "legacy-rs256-2026-08",
            "legacy-service-client-legacy-web-secret-sha256": "a" * 64,
            "legacy-postgres-customer-password": "password",
        }

    def test_accepts_matching_rsa_pkcs8_spki_pair_and_key_id(self) -> None:
        payload = self.valid_payload()
        self.assertEqual(validate_value_shapes(payload, set(payload)), [])

    def test_rejects_arbitrary_base64_as_private_key(self) -> None:
        payload = self.valid_payload()
        payload["legacy-jwt-private-key"] = base64.b64encode(b"key-material" * 3).decode("ascii")
        self.assertEqual(
            validate_value_shapes(payload, set(payload)),
            ["legacy-jwt-private-key", "legacy-jwt-public-key"],
        )

    def test_rejects_malformed_multiple_and_trailing_pem_material(self) -> None:
        invalid_private_values = (
            "-----BEGIN PRIVATE KEY-----\nnot-base64\n-----END PRIVATE KEY-----\n",
            self.private_pem + self.private_pem,
            self.private_pem + "trailing text",
            self.private_pem.replace("BEGIN PRIVATE KEY", "BEGIN RSA PRIVATE KEY").replace(
                "END PRIVATE KEY", "END RSA PRIVATE KEY"
            ),
        )
        for value in invalid_private_values:
            with self.subTest(value_length=len(value)):
                payload = self.valid_payload()
                payload["legacy-jwt-private-key"] = value
                self.assertIn(
                    "legacy-jwt-private-key",
                    validate_value_shapes(payload, set(payload)),
                )

    def test_rejects_mismatched_public_key(self) -> None:
        payload = self.valid_payload()
        payload["legacy-jwt-public-key"] = self.other_public_pem
        self.assertEqual(
            validate_value_shapes(payload, set(payload)),
            ["legacy-jwt-private-key", "legacy-jwt-public-key"],
        )

    def test_rejects_rsa_keys_below_2048_bits(self) -> None:
        weak_key = rsa.generate_private_key(public_exponent=65537, key_size=1024)
        payload = self.valid_payload()
        payload["legacy-jwt-private-key"] = weak_key.private_bytes(
            serialization.Encoding.PEM,
            serialization.PrivateFormat.PKCS8,
            serialization.NoEncryption(),
        ).decode("ascii")
        payload["legacy-jwt-public-key"] = weak_key.public_key().public_bytes(
            serialization.Encoding.PEM,
            serialization.PublicFormat.SubjectPublicKeyInfo,
        ).decode("ascii")

        self.assertEqual(
            validate_value_shapes(payload, set(payload)),
            ["legacy-jwt-private-key", "legacy-jwt-public-key"],
        )

    def test_rejects_invalid_key_ids(self) -> None:
        for value in ("", "contains space", "line\nbreak", ".starts-with-dot", "x" * 129):
            with self.subTest(value=value):
                payload = self.valid_payload()
                payload["legacy-jwt-key-id"] = value
                self.assertIn(
                    "legacy-jwt-key-id",
                    validate_value_shapes(payload, set(payload)),
                )

    def test_rejects_invalid_properties_without_returning_values(self) -> None:
        payload = self.valid_payload()
        payload.update(
            {
                "legacy-service-client-legacy-web-secret-sha256": "not-a-hash",
                "legacy-postgres-customer-password": "line\nbreak",
                "legacy-postgres-order-password": "",
            }
        )
        invalid = validate_value_shapes(payload, set(payload))
        self.assertEqual(
            invalid,
            [
                "legacy-postgres-customer-password",
                "legacy-postgres-order-password",
                "legacy-service-client-legacy-web-secret-sha256",
            ],
        )
        self.assertNotIn("not-a-hash", invalid)
        self.assertNotIn("line\nbreak", invalid)


if __name__ == "__main__":
    unittest.main()
