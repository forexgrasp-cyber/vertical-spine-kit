"""Shared canonical booking service wrapper for vertical-spine-kit.

Delegates to shared.booking.service.BookingService for centralized
availability / conflict enforcement.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Optional
from uuid import UUID, uuid4

from shared.base.base_service import ServiceResponse
from shared.booking.models import BookingCreate
from shared.booking.service import BookingService as SharedBookingService


class BookingService:
    """Vertical booking facade over the shared canonical booking service."""

    def __init__(self, tenant_id: str = "00000000-0000-0000-0000-000000000000", db_path: Optional[Path] = None) -> None:
        self.tenant_id = tenant_id
        self._shared = SharedBookingService(in_memory=True, tenant_id=tenant_id)

    def create(self, name: str = "", **_kwargs: Any) -> ServiceResponse:
        if not name or not name.strip():
            return ServiceResponse.fail("Name is required")
        now = datetime.now(timezone.utc).replace(tzinfo=None)
        booking = BookingCreate(
            customer_name=name.strip(),
            staff_id=uuid4(),
            service_type="general",
            start_time=now,
            end_time=now + timedelta(hours=1),
        )
        return self._shared.create(booking)

    def get(self, item_id: str) -> ServiceResponse:
        try:
            return self._shared.get(UUID(item_id))
        except (ValueError, AttributeError):
            return ServiceResponse.fail("Not found")

    def list_all(self) -> ServiceResponse:
        return self._shared.list()

    def delete(self, item_id: str) -> ServiceResponse:
        try:
            return self._shared.delete(UUID(item_id))
        except (ValueError, AttributeError):
            return ServiceResponse.fail("Not found")
