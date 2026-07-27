from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
CONTRACT_PATH = REPO_ROOT / "3-apps/_legacy-postgres/readiness/legacy-secret-contract.json"


def load_contract() -> dict:
    return json.loads(CONTRACT_PATH.read_text(encoding="utf-8"))


def read_live_keys(project: str, secret: str) -> set[str]:
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
    return set(payload)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Validate the legacy Secret Manager key contract without printing values."
    )
    parser.add_argument(
        "--live",
        action="store_true",
        help="Read the latest Secret Manager version through gcloud (read-only).",
    )
    args = parser.parse_args()

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
        live = read_live_keys(manager["project"], manager["secret"])
        report["liveKeyCount"] = len(live)
        report["missingFromLive"] = sorted(expected - live)
        report["uncataloguedLiveKeys"] = sorted(live - expected)
        report["matchesCatalog"] = live == expected
    else:
        report["liveCheck"] = "not requested"

    print(json.dumps(report, sort_keys=True))
    if args.live and not report["matchesCatalog"]:
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
