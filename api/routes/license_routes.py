"""License-key routes (#5) for vertical-spine-kit sales.

Mounted by main.py at prefix="/api/v1/licenses".

- POST   /api/v1/licenses/mint     -> issue a new VSK-... key (admin)
- POST   /api/v1/licenses/verify   -> statelessly verify a key (buyer, offline-capable)
- GET    /api/v1/licenses/{key}    -> lookup a key's status
- GET    /api/v1/licenses          -> list issued keys (admin)
- POST   /api/v1/licenses/{key}/revoke -> kill-list a key (admin)
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status

from services.auth import require_license
from services.license_service import LicenseInfo, LicenseService

router = APIRouter(tags=["licenses"])


def _svc() -> LicenseService:
    return LicenseService()


class MintRequest(dict):
    pass


@router.post("/mint", status_code=status.HTTP_201_CREATED)
def mint_license_key(payload: dict[str, Any]) -> dict[str, Any]:
    holder = str(payload.get("holder", ""))
    svc = _svc()
    info = svc.mint(holder=holder)
    return {"key": info.key, "holder": info.holder, "issued_at": info.issued_at}


@router.post("/verify")
def verify_license_key(payload: dict[str, Any]) -> dict[str, Any]:
    key = str(payload.get("key", ""))
    revoked = payload.get("revoked") or []
    svc = _svc()
    try:
        info = svc.verify_revoked(key, revoked=revoked)
    except Exception as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    return {"valid": True, "key": info.key, "holder": info.holder, "issued_at": info.issued_at}


@router.get("/validate")
def validate_license(
    license: LicenseInfo = Depends(require_license),
) -> dict[str, Any]:
    """Validate a license key (X-License-Key header) without requiring user auth."""
    return {"valid": True, "key": license.key, "holder": license.holder, "issued_at": license.issued_at}


@router.get("/{key}")
def get_license(key: str) -> dict[str, Any]:
    svc = _svc()
    for row in svc.list_keys(include_revoked=True):
        if row["key"] == key:
            return {
                "key": row["key"],
                "holder": row["holder"],
                "issued_at": row["issued_at"],
                "revoked": bool(row.get("revoked")),
            }
    raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="license key not found")


@router.get("")
def list_licenses(payload: dict[str, Any] | None = None) -> dict[str, Any]:
    include_revoked = bool((payload or {}).get("include_revoked"))
    svc = _svc()
    return {"licenses": svc.list_keys(include_revoked=include_revoked), "stats": svc.stats()}


@router.post("/{key}/revoke")
def revoke_license(key: str) -> dict[str, Any]:
    svc = _svc()
    if not svc.revoke(key):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="license key not found")
    return {"key": key, "revoked": True}
