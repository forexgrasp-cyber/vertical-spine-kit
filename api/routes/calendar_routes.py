"""Shared calendar API routes for vertical-spine-kit.

Exposes the shared canonical CalendarService as HTTP endpoints.
Mounted by main.py with prefix="/api/v1/calendar".
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, ConfigDict, Field

from services.auth import get_current_user
from services.calendar_service import CalendarService

# No prefix here - main.py mounts with prefix="/api/v1/calendar"
router = APIRouter(tags=["calendar"])


class CalendarEventCreateRequest(BaseModel):
    title: str = Field(..., min_length=1, max_length=200)
    start_time: Optional[datetime] = None
    end_time: Optional[datetime] = None
    staff_id: Optional[str] = None


class CalendarEventUpdateRequest(BaseModel):
    title: Optional[str] = Field(default=None, min_length=1, max_length=200)
    start_time: Optional[datetime] = None
    end_time: Optional[datetime] = None
    staff_id: Optional[str] = None


class CalendarEventResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    title: str
    start_time: str
    end_time: str
    staff_id: Optional[UUID]
    event_type: str
    created_at: str
    updated_at: str


class CalendarEventListResponse(BaseModel):
    items: list[CalendarEventResponse]
    total: int


def _get_calendar_service() -> CalendarService:
    return CalendarService()


@router.post("", response_model=CalendarEventResponse, status_code=status.HTTP_201_CREATED)
def create_calendar_event(
    data: CalendarEventCreateRequest,
    current_user: dict = Depends(get_current_user),
    service: CalendarService = Depends(_get_calendar_service),
) -> CalendarEventResponse:
    """Create a new calendar event."""
    result = service.create(title=data.title, start_time=data.start_time, end_time=data.end_time, staff_id=data.staff_id)
    if not result.success:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=result.error)
    e = result.data
    return CalendarEventResponse(
        id=e.id,
        title=e.title,
        start_time=e.start_time.isoformat(),
        end_time=e.end_time.isoformat(),
        staff_id=e.staff_id,
        event_type=e.event_type,
        created_at=e.created_at.isoformat(),
        updated_at=e.updated_at.isoformat(),
    )


@router.get("", response_model=CalendarEventListResponse)
def list_calendar_events(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    current_user: dict = Depends(get_current_user),
    service: CalendarService = Depends(_get_calendar_service),
) -> CalendarEventListResponse:
    """List calendar events."""
    result = service.list_all()
    if not result.success:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=result.error)
    items = result.data or []
    return CalendarEventListResponse(
        items=[
            CalendarEventResponse(
                id=e.id,
                title=e.title,
                start_time=e.start_time.isoformat(),
                end_time=e.end_time.isoformat(),
                staff_id=e.staff_id,
                event_type=e.event_type,
                created_at=e.created_at.isoformat(),
                updated_at=e.updated_at.isoformat(),
            )
            for e in items
        ],
        total=len(items),
    )


@router.get("/{event_id}", response_model=CalendarEventResponse)
def get_calendar_event(
    event_id: UUID,
    current_user: dict = Depends(get_current_user),
    service: CalendarService = Depends(_get_calendar_service),
) -> CalendarEventResponse:
    """Get calendar event by ID."""
    result = service.get(str(event_id))
    if not result.success or result.data is None:
        raise HTTPException(status_code=404, detail="Calendar event not found")
    e = result.data
    return CalendarEventResponse(
        id=e.id,
        title=e.title,
        start_time=e.start_time.isoformat(),
        end_time=e.end_time.isoformat(),
        staff_id=e.staff_id,
        event_type=e.event_type,
        created_at=e.created_at.isoformat(),
        updated_at=e.updated_at.isoformat(),
    )


@router.delete("/{event_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_calendar_event(
    event_id: UUID,
    current_user: dict = Depends(get_current_user),
    service: CalendarService = Depends(_get_calendar_service),
) -> None:
    """Delete calendar event."""
    result = service.delete(str(event_id))
    if not result.success:
        raise HTTPException(status_code=404, detail="Calendar event not found")
