from __future__ import annotations

import base64
import unittest

from scripts.validate_legacy_secret_contract import validate_value_shapes


class SecretContractValueValidationTests(unittest.TestCase):
    def test_accepts_non_empty_values_encoded_key_material_and_hashes(self) -> None:
        key = base64.b64encode(b"key-material" * 4).decode("ascii")
        payload = {
            "legacy-jwt-private-key": key,
            "legacy-jwt-public-key": "-----BEGIN PUBLIC KEY-----\\nkey\\n-----END PUBLIC KEY-----",
            "legacy-service-client-legacy-web-secret-sha256": "a" * 64,
            "legacy-postgres-customer-password": "password",
        }

        self.assertEqual(
            validate_value_shapes(payload, set(payload)),
            [],
        )

    def test_rejects_invalid_properties_without_returning_values(self) -> None:
        payload = {
            "legacy-jwt-private-key": "too-short",
            "legacy-jwt-public-key": "-----BEGIN PUBLIC KEY-----",
            "legacy-service-client-legacy-web-secret-sha256": "not-a-hash",
            "legacy-postgres-customer-password": "line\nbreak",
            "legacy-postgres-order-password": "",
        }

        invalid = validate_value_shapes(payload, set(payload))

        self.assertEqual(
            invalid,
            [
                "legacy-jwt-private-key",
                "legacy-jwt-public-key",
                "legacy-postgres-customer-password",
                "legacy-postgres-order-password",
                "legacy-service-client-legacy-web-secret-sha256",
            ],
        )
        self.assertNotIn("too-short", invalid)
        self.assertNotIn("line\nbreak", invalid)


if __name__ == "__main__":
    unittest.main()
