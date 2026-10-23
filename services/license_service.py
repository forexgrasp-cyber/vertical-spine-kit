"""License-key sales service (#5) for vertical-spine-kit.

Mints and verifies HMAC-signed ``VSK-...`` keys via the shared canonical
``shared.digital_products.license_keys`` module. Persists issued keys to a
per-vertical JSON store so the kit can track what's been sold (the signature
verification itself is stateless and works offline at scaffold time).

Storage: ``data/license_keys.json`` (JSON array of {key, holder, issued_at}).
All methods are sync (no async DB dependency for the kit's license surface).
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from shared.digital_products import LicenseInfo, mint_license, verify_license

_STORE_DEFAULT = str(Path(__file__).resolve().parent.parent / "data" / "license_keys.json")


class LicenseService:
    """Mint + verify license keys with a persistent issuance ledger."""

    def __init__(self, store_path: Path | None = None) -> None:
        if store_path is None:
            store_path = Path(os.environ.get("LICENSE_STORE_PATH", _STORE_DEFAULT))
        self.store_path = store_path
        self._ensure_store()

    def _ensure_store(self) -> None:
        if not self.store_path.exists():
            self.store_path.parent.mkdir(parents=True, exist_ok=True)
            self.store_path.write_text("[]", encoding="utf-8")

    def _read(self) -> list[dict[str, Any]]:
        try:
            return json.loads(self.store_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return []

    def _write(self, rows: list[dict[str, Any]]) -> None:
        self.store_path.write_text(json.dumps(rows, indent=2), encoding="utf-8")

    # ── public API ────────────────────────────────────────────────────────

    def mint(self, holder: str = "") -> LicenseInfo:
        """Issue a new key and record it in the ledger."""
        info = mint_license(holder=holder)
        rows = self._read()
        rows.append(
            {
                "key": info.key,
                "holder": info.holder,
                "issued_at": info.issued_at,
                "revoked": False,
            }
        )
        self._write(rows)
        return info

    def verify(self, key: str) -> LicenseInfo:
        """Statelessly verify a key against the signing secret.

        Does not consult the revocation list here - callers that want
        kill-list support pass ``revoked`` explicitly via ``verify_revoked``.
        """
        return verify_license(key)

    def verify_revoked(self, key: str, revoked: list[str] | None = None) -> LicenseInfo:
        """Verify a key and reject revoked ones."""
        rows = self._read()
        revoked_keys = {r["key"] for r in rows if r.get("revoked")}
        if revoked:
            revoked_keys |= set(revoked)
        return verify_license(key, revoked=revoked_keys)
    def revoke(self, key: str) -> bool:
        """Mark a key revoked (kill-list). Returns False if unknown or already revoked."""
        rows = self._read()
        changed = False
        for row in rows:
            if row["key"] == key:
                if not row.get("revoked"):
                    row["revoked"] = True
                    changed = True
                break
        if changed:
            self._write(rows)
        return changed

    def list_keys(self, include_revoked: bool = False) -> list[dict[str, Any]]:
        rows = self._read()
        if not include_revoked:
            rows = [r for r in rows if not r.get("revoked")]
        return rows

    def stats(self) -> dict[str, Any]:
        rows = self._read()
        return {
            "issued": len(rows),
            "active": sum(1 for r in rows if not r.get("revoked")),
            "revoked": sum(1 for r in rows if r.get("revoked")),
        }
