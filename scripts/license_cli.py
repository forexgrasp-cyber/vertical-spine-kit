"""CLI for minting / verifying vertical-spine-kit license keys (#5).

Usage:
    py scripts/license_cli.py mint [--holder "Acme Corp"]
    py scripts/license_cli.py verify VSK-XXXX-XXXX-...
    py scripts/license_cli.py stats

Env:
    LICENSE_SIGNING_SECRET  (required - HMAC secret for mint/verify)
    LICENSE_STORE_PATH      (optional - defaults to data/license_keys.json)
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from services.license_service import LicenseError, LicenseService  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser(description="vertical-spine-kit license-key tool")
    sub = ap.add_subparsers(dest="command", required=True)

    p_mint = sub.add_parser("mint", help="issue a new VSK-... license key")
    p_mint.add_argument("--holder", default="", help="holder tag bound to the key")

    p_verify = sub.add_parser("verify", help="statelessly verify a license key")
    p_verify.add_argument("key", help="the VSK-... key to verify")

    sub.add_parser("stats", help="issuance stats from the ledger")

    args = ap.parse_args()
    svc = LicenseService()

    if args.command == "mint":
        try:
            info = svc.mint(holder=args.holder)
        except LicenseError as exc:
            print(f"error: {exc}", file=sys.stderr)
            return 1
        print(info.key)
        return 0

    if args.command == "verify":
        try:
            info = svc.verify_revoked(args.key)
        except LicenseError as exc:
            print(f"invalid: {exc}")
            return 1
        print(f"valid  key={info.key} holder={info.holder or '(none)'} issued_at={info.issued_at}")
        return 0

    if args.command == "stats":
        print(svc.stats())
        return 0

    return 1


if __name__ == "__main__":
    raise SystemExit(main())
