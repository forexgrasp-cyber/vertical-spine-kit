"""Shared meeting API routes for vertical-spine-kit.

Exposes the shared canonical MeetingService as HTTP endpoints.
Mounted by main.py with prefix="/api/v1/meetings".
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, ConfigDict, Field

from services.auth import get_current_user
from services.meeting_service import MeetingService

# No prefix here - main.py mounts with prefix="/api/v1/meetings"
router = APIRouter(tags=["meetings"])


class MeetingCreateRequest(BaseModel):
    title: str = Field(..., min_length=1, max_length=200)
    start_time: Optional[datetime] = None
    end_time: Optional[datetime] = None
    staff_id: Optional[str] = None
    customer_id: Optional[str] = None


class MeetingUpdateRequest(BaseModel):
    title: Optional[str] = Field(default=None, min_length=1, max_length=200)
    start_time: Optional[datetime] = None
    end_time: Optional[datetime] = None
    staff_id: Optional[str] = None
    customer_id: Optional[str] = None
    status: Optional[str] = None


class MeetingResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    title: str
    start_time: str
    end_time: str
    staff_id: Optional[UUID]
    customer_id: Optional[UUID]
    status: str
    meeting_type: str
    created_at: str
    updated_at: str


class MeetingListResponse(BaseModel):
    items: list[MeetingResponse]
    total: int


def _get_meeting_service() -> MeetingService:
    return MeetingService()


@router.post("", response_model=MeetingResponse, status_code=status.HTTP_201_CREATED)
def create_meeting(
    data: MeetingCreateRequest,
    current_user: dict = Depends(get_current_user),
    service: MeetingService = Depends(_get_meeting_service),
) -> MeetingResponse:
    """Create a new meeting."""
    result = service.create(
        title=data.title,
        start_time=data.start_time,
        end_time=data.end_time,
        staff_id=data.staff_id,
        customer_id=data.customer_id,
    )
    if not result.success:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=result.error)
    m = result.data
    return MeetingResponse(
        id=m.id,
        title=m.title,
        start_time=m.start_time.isoformat(),
        end_time=m.end_time.isoformat(),
        staff_id=m.staff_id,
        customer_id=m.customer_id,
        status=m.status,
        meeting_type=m.meeting_type,
        created_at=m.created_at.isoformat(),
        updated_at=m.updated_at.isoformat(),
    )


@router.get("", response_model=MeetingListResponse)
def list_meetings(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    current_user: dict = Depends(get_current_user),
    service: MeetingService = Depends(_get_meeting_service),
) -> MeetingListResponse:
    """List meetings."""
    result = service.list_all()
    if not result.success:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=result.error)
    items = result.data or []
    return MeetingListResponse(
        items=[
            MeetingResponse(
                id=m.id,
                title=m.title,
                start_time=m.start_time.isoformat(),
                end_time=m.end_time.isoformat(),
                staff_id=m.staff_id,
                customer_id=m.customer_id,
                status=m.status,
                meeting_type=m.meeting_type,
                created_at=m.created_at.isoformat(),
                updated_at=m.updated_at.isoformat(),
            )
            for m in items
        ],
        total=len(items),
    )


@router.get("/{meeting_id}", response_model=MeetingResponse)
def get_meeting(
    meeting_id: UUID,
    current_user: dict = Depends(get_current_user),
    service: MeetingService = Depends(_get_meeting_service),
) -> MeetingResponse:
    """Get meeting by ID."""
    result = service.get(str(meeting_id))
    if not result.success or result.data is None:
        raise HTTPException(status_code=404, detail="Meeting not found")
    m = result.data
    return MeetingResponse(
        id=m.id,
        title=m.title,
        start_time=m.start_time.isoformat(),
        end_time=m.end_time.isoformat(),
        staff_id=m.staff_id,
        customer_id=m.customer_id,
        status=m.status,
        meeting_type=m.meeting_type,
        created_at=m.created_at.isoformat(),
        updated_at=m.updated_at.isoformat(),
    )


@router.delete("/{meeting_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_meeting(
    meeting_id: UUID,
    current_user: dict = Depends(get_current_user),
    service: MeetingService = Depends(_get_meeting_service),
) -> None:
    """Delete meeting."""
    result = service.delete(str(meeting_id))
    if not result.success:
        raise HTTPException(status_code=404, detail="Meeting not found")
