"""Shared canonical meeting service wrapper for vertical-spine-kit.

Delegates to shared.meeting.service.MeetingService for staff/customer
availability-aware meeting scheduling.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Optional
from uuid import UUID

from shared.base.base_service import ServiceResponse
from shared.meeting.models import MeetingCreate
from shared.meeting.service import MeetingService as SharedMeetingService


class MeetingService:
    """Vertical meeting facade over the shared canonical meeting service."""

    def __init__(self, tenant_id: str = "00000000-0000-0000-0000-000000000000", db_path: Optional[Path] = None) -> None:
        self.tenant_id = tenant_id
        self._shared = SharedMeetingService(in_memory=True, tenant_id=tenant_id)

    def create(self, title: str = "", start_time: datetime | None = None, end_time: datetime | None = None, staff_id: str | None = None, customer_id: str | None = None, **_kwargs: Any) -> ServiceResponse:
        if not title or not title.strip():
            return ServiceResponse.fail("Title is required")
        now = datetime.now()
        start = start_time or now
        end = end_time or (now + timedelta(hours=1))
        staff_uuid = UUID(staff_id) if staff_id else None
        customer_uuid = UUID(customer_id) if customer_id else None
        data = MeetingCreate(
            title=title.strip(),
            start_time=start,
            end_time=end,
            staff_id=staff_uuid,
            customer_id=customer_uuid,
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

    def list_by_customer(self, customer_id: str) -> ServiceResponse:
        try:
            return self._shared.list_by_customer(UUID(customer_id))
        except (ValueError, AttributeError):
            return ServiceResponse.fail("Not found")

    def confirm(self, item_id: str) -> ServiceResponse:
        try:
            return self._shared.confirm(UUID(item_id))
        except (ValueError, AttributeError):
            return ServiceResponse.fail("Not found")
