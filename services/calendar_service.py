"""Shared canonical calendar service wrapper for vertical-spine-kit.

Delegates to shared.calendar.service.CalendarService for event management
and available-slot generation.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Optional
from uuid import UUID

from shared.base.base_service import ServiceResponse
from shared.calendar.models import CalendarEventCreate
from shared.calendar.service import CalendarService as SharedCalendarService


class CalendarService:
    """Vertical calendar facade over the shared canonical calendar service."""

    def __init__(self, tenant_id: str = "00000000-0000-0000-0000-000000000000", db_path: Optional[Path] = None) -> None:
        self.tenant_id = tenant_id
        self._shared = SharedCalendarService(in_memory=True, tenant_id=tenant_id)

    def create(self, title: str = "", start_time: datetime | None = None, end_time: datetime | None = None, staff_id: str | None = None, **_kwargs: Any) -> ServiceResponse:
        if not title or not title.strip():
            return ServiceResponse.fail("Title is required")
        now = datetime.now()
        start = start_time or now
        end = end_time or (now + timedelta(hours=1))
        staff_uuid = UUID(staff_id) if staff_id else None
        data = CalendarEventCreate(
            title=title.strip(),
            start_time=start,
            end_time=end,
            staff_id=staff_uuid,
        )
        return self._shared.create(data)

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

    def list_by_staff(self, staff_id: str) -> ServiceResponse:
        try:
            return self._shared.list_by_staff(UUID(staff_id))
        except (ValueError, AttributeError):
            return ServiceResponse.fail("Not found")

    def available_slots(self, staff_id: str, day_start: datetime, day_end: datetime, slot_minutes: int = 30) -> ServiceResponse:
        try:
            return self._shared.available_slots(UUID(staff_id), day_start, day_end, slot_minutes)
        except (ValueError, AttributeError):
            return ServiceResponse.fail("Not found")
