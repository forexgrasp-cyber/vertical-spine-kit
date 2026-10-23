"""Shared canonical staff service wrapper for vertical-spine-kit.

Delegates to shared.staff.service.StaffService for tenant-scoped staff
management.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Optional
from uuid import UUID

from shared.base.base_service import ServiceResponse
from shared.staff.models import StaffCreate
from shared.staff.service import StaffService as SharedStaffService


class StaffService:
    """Vertical staff facade over the shared canonical staff service."""

    def __init__(self, tenant_id: str = "00000000-0000-0000-0000-000000000000", db_path: Optional[Path] = None) -> None:
        self.tenant_id = tenant_id
        self._shared = SharedStaffService(in_memory=True, tenant_id=tenant_id)

    def create(self, name: str = "", role: str = "cleaner", skills: list[str] | None = None, **_kwargs: Any) -> ServiceResponse:
        if not name or not name.strip():
            return ServiceResponse.fail("Name is required")
        data = StaffCreate(name=name.strip(), role=role, skills=list(skills or []))
        return self._shared.create(data)

    def get(self, item_id: str) -> ServiceResponse:
        try:
            return self._shared.get(UUID(item_id))
        except (ValueError, AttributeError):
            return ServiceResponse.fail("Not found")

    def list_all(self) -> ServiceResponse:
        return self._shared.list_active()

    def delete(self, item_id: str) -> ServiceResponse:
        try:
            return self._shared.delete(UUID(item_id))
        except (ValueError, AttributeError):
            return ServiceResponse.fail("Not found")

    def list_by_skill(self, skill: str) -> ServiceResponse:
        return self._shared.list_by_skill(skill)

    def count_by_status(self) -> ServiceResponse:
        return self._shared.count_by_status()
