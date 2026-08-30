from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa


REPO_ROOT = Path(__file__).resolve().parents[1]
CONTRACT_PATH = REPO_ROOT / "3-apps/_legacy-postgres/readiness/legacy-secret-contract.json"
PRIVATE_KEY_NAME = "legacy-jwt-private-key"
PUBLIC_KEY_NAME = "legacy-jwt-public-key"
KEY_ID_NAME = "legacy-jwt-key-id"


def pem_pattern(label: str) -> re.Pattern[str]:
    escaped_label = re.escape(label)
    return re.compile(
        rf"-----BEGIN {escaped_label}-----\r?\n(?:[A-Za-z0-9+/]{{1,64}}={{0,2}}\r?\n)+"
        rf"-----END {escaped_label}-----(?:\r?\n)?\Z"
    )


PRIVATE_KEY_PEM = pem_pattern("PRIVATE KEY")
PUBLIC_KEY_PEM = pem_pattern("PUBLIC KEY")
KEY_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,127}\Z")


def load_contract() -> dict:
    return json.loads(CONTRACT_PATH.read_text(encoding="utf-8"))


def read_live_payload(project: str, secret: str) -> dict[str, object]:
    gcloud = shutil.which("gcloud") or shutil.which("gcloud.cmd")
    if not gcloud:
        raise RuntimeError("gcloud CLI is required for --live")
    result = subprocess.run(
        [
            gcloud,
            "secrets",
            "versions",
            "access",
            "latest",
            f"--project={project}",
            f"--secret={secret}",
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    payload = json.loads(result.stdout)
    if not isinstance(payload, dict):
        raise ValueError("Secret Manager payload is not a flat JSON object")
    return payload


def validate_value_shapes(payload: dict[str, object], expected: set[str]) -> list[str]:
    """Return property names whose values cannot be safely projected.

    This deliberately reports names only.  Secret values are never included in
    diagnostics, exceptions, or the command output.
    """

    invalid: list[str] = []
    key_material_names = {PRIVATE_KEY_NAME, PUBLIC_KEY_NAME}
    for name in sorted(expected):
        value = payload.get(name)
        if not isinstance(value, str) or not value.strip():
            invalid.append(name)
        elif name not in key_material_names and ("\r" in value or "\n" in value):
            invalid.append(name)

    for name in sorted(expected):
        value = payload.get(name)
        if not isinstance(value, str) or name in invalid:
            continue
        if name.endswith("-secret-sha256") and not re.fullmatch(r"[0-9a-fA-F]{64}", value):
            invalid.append(name)
        elif name == KEY_ID_NAME and not KEY_ID.fullmatch(value):
            invalid.append(name)

    private_value = payload.get(PRIVATE_KEY_NAME)
    public_value = payload.get(PUBLIC_KEY_NAME)
    if PRIVATE_KEY_NAME in expected or PUBLIC_KEY_NAME in expected:
        key_pair_invalid = False
        private_key = None
        public_key = None
        if not isinstance(private_value, str) or not PRIVATE_KEY_PEM.fullmatch(private_value):
            key_pair_invalid = True
        else:
            try:
                private_key = serialization.load_pem_private_key(
                    private_value.encode("ascii"),
                    password=None,
                )
            except (TypeError, ValueError, UnicodeEncodeError):
                key_pair_invalid = True
            else:
                if not isinstance(private_key, rsa.RSAPrivateKey) or private_key.key_size < 2048:
                    key_pair_invalid = True

        if not isinstance(public_value, str) or not PUBLIC_KEY_PEM.fullmatch(public_value):
            key_pair_invalid = True
        else:
            try:
                public_key = serialization.load_pem_public_key(public_value.encode("ascii"))
            except (TypeError, ValueError, UnicodeEncodeError):
                key_pair_invalid = True
            else:
                if not isinstance(public_key, rsa.RSAPublicKey) or public_key.key_size < 2048:
                    key_pair_invalid = True

        if private_key is not None and public_key is not None:
            if private_key.public_key().public_numbers() != public_key.public_numbers():
                key_pair_invalid = True

        if key_pair_invalid:
            if PRIVATE_KEY_NAME in expected:
                invalid.append(PRIVATE_KEY_NAME)
            if PUBLIC_KEY_NAME in expected:
                invalid.append(PUBLIC_KEY_NAME)

    return sorted(set(invalid))


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Validate the legacy Secret Manager key contract without printing values."
    )
    parser.add_argument(
        "--live",
        action="store_true",
        help="Read the latest Secret Manager version through gcloud (read-only).",
    )
    parser.add_argument(
        "--validate-values",
        action="store_true",
        help="Validate safe value shapes for present properties; requires --live and never prints values.",
    )
    args = parser.parse_args()

    if args.validate_values and not args.live:
        parser.error("--validate-values requires --live")

    contract = load_contract()
    manager = contract["secretManager"]
    expected = set(contract["presentProperties"])
    report: dict[str, object] = {
        "secret": manager["secret"],
        "catalogPresentKeyCount": len(expected),
        "pendingKeyCount": len(contract["pendingProperties"]),
        "valuesPrinted": False,
    }

    if args.live:
        live_payload = read_live_payload(manager["project"], manager["secret"])
        live = set(live_payload)
        report["liveKeyCount"] = len(live)
        report["missingFromLive"] = sorted(expected - live)
        report["uncataloguedLiveKeys"] = sorted(live - expected)
        report["matchesCatalog"] = live == expected
        if args.validate_values:
            invalid_properties = validate_value_shapes(live_payload, expected)
            report["valueValidation"] = {
                "valid": not invalid_properties,
                "invalidProperties": invalid_properties,
                "valuesPrinted": False,
            }
    else:
        report["liveCheck"] = "not requested"

    print(json.dumps(report, sort_keys=True))
    if args.live and not report["matchesCatalog"]:
        return 1
    if args.validate_values and not report["valueValidation"]["valid"]:
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
