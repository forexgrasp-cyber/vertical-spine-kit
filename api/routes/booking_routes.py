"""Shared booking API routes for vertical-spine-kit.

Exposes the shared canonical BookingService as HTTP endpoints.
Mounted by main.py with prefix="/api/v1/bookings".
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, ConfigDict, Field

from services.auth import get_current_user
from services.booking_service import BookingService

# No prefix here - main.py mounts with prefix="/api/v1/bookings"
router = APIRouter(tags=["bookings"])


class BookingCreateRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=200)
    service_type: str = Field(default="general", max_length=100)
    start_time: Optional[datetime] = None
    end_time: Optional[datetime] = None


class BookingUpdateRequest(BaseModel):
    name: Optional[str] = Field(default=None, min_length=1, max_length=200)
    service_type: Optional[str] = Field(default=None, max_length=100)
    start_time: Optional[datetime] = None
    end_time: Optional[datetime] = None
    status: Optional[str] = None


class BookingResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    customer_name: str
    service_type: str
    start_time: str
    end_time: str
    status: str
    created_at: str
    updated_at: str


class BookingListResponse(BaseModel):
    items: list[BookingResponse]
    total: int


def _get_service() -> BookingService:
    return BookingService()


@router.post("", response_model=BookingResponse, status_code=status.HTTP_201_CREATED)
def create_booking(
    data: BookingCreateRequest,
    current_user: dict = Depends(get_current_user),
    service: BookingService = Depends(_get_service),
) -> BookingResponse:
    """Create a new booking."""
    result = service.create(name=data.name)
    if not result.success:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=result.error)
    data_obj = result.data
    return BookingResponse(
        id=data_obj.id,
        customer_name=data_obj.customer_name,
        service_type=data_obj.service_type,
        start_time=data_obj.start_time.isoformat(),
        end_time=data_obj.end_time.isoformat(),
        status=data_obj.status,
        created_at=data_obj.created_at.isoformat(),
        updated_at=data_obj.updated_at.isoformat(),
    )


@router.get("", response_model=BookingListResponse)
def list_bookings(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    current_user: dict = Depends(get_current_user),
    service: BookingService = Depends(_get_service),
) -> BookingListResponse:
    """List bookings."""
    result = service.list_all()
    if not result.success:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=result.error)
    items = result.data or []
    return BookingListResponse(
        items=[
            BookingResponse(
                id=b.id,
                customer_name=b.customer_name,
                service_type=b.service_type,
                start_time=b.start_time.isoformat(),
                end_time=b.end_time.isoformat(),
                status=b.status,
                created_at=b.created_at.isoformat(),
                updated_at=b.updated_at.isoformat(),
            )
            for b in items
        ],
        total=len(items),
    )


@router.get("/{booking_id}", response_model=BookingResponse)
def get_booking(
    booking_id: UUID,
    current_user: dict = Depends(get_current_user),
    service: BookingService = Depends(_get_service),
) -> BookingResponse:
    """Get booking by ID."""
    result = service.get(str(booking_id))
    if not result.success or result.data is None:
        raise HTTPException(status_code=404, detail="Booking not found")
    b = result.data
    return BookingResponse(
        id=b.id,
        customer_name=b.customer_name,
        service_type=b.service_type,
        start_time=b.start_time.isoformat(),
        end_time=b.end_time.isoformat(),
        status=b.status,
        created_at=b.created_at.isoformat(),
        updated_at=b.updated_at.isoformat(),
    )


@router.delete("/{booking_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_booking(
    booking_id: UUID,
    current_user: dict = Depends(get_current_user),
    service: BookingService = Depends(_get_service),
) -> None:
    """Delete booking."""
    result = service.delete(str(booking_id))
    if not result.success:
        raise HTTPException(status_code=404, detail="Booking not found")
