from __future__ import annotations

import unittest
from pathlib import Path

import yaml


REPO_ROOT = Path(__file__).resolve().parents[1]


class LegacyJwtProjectionEncodingTests(unittest.TestCase):
    def test_every_public_key_projection_base64_encodes_the_raw_spki_pem(self) -> None:
        manifests = sorted((REPO_ROOT / "3-apps").glob("_legacy-*/base/external-secret.yaml"))
        projections: list[tuple[Path, str]] = []
        for manifest in manifests:
            document = yaml.safe_load(manifest.read_text(encoding="utf-8"))
            template = document.get("spec", {}).get("target", {}).get("template", {}).get("data", {})
            if "Jwt__PublicKey" in template:
                projections.append((manifest, template["Jwt__PublicKey"]))

        self.assertTrue(projections, "expected at least one legacy JWT public-key projection")
        expected = "{{ .jwtPublicKey | b64enc }}"
        for manifest, value in projections:
            with self.subTest(manifest=manifest.relative_to(REPO_ROOT)):
                self.assertEqual(value, expected)


if __name__ == "__main__":
    unittest.main()
