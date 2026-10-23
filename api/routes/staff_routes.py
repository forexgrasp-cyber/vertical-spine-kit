"""Shared staff API routes for vertical-spine-kit.

Exposes the shared canonical StaffService as HTTP endpoints.
Mounted by main.py with prefix="/api/v1/staff".
"""

from __future__ import annotations

from typing import Any, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, ConfigDict, Field

from services.auth import get_current_user
from services.staff_service import StaffService

# No prefix here - main.py mounts with prefix="/api/v1/staff"
router = APIRouter(tags=["staff"])


class StaffCreateRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=200)
    role: str = Field(default="cleaner", max_length=50)
    skills: list[str] = Field(default_factory=list)


class StaffUpdateRequest(BaseModel):
    name: Optional[str] = Field(default=None, min_length=1, max_length=200)
    role: Optional[str] = Field(default=None, max_length=50)
    skills: Optional[list[str]] = None
    status: Optional[str] = None


class StaffResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    name: str
    role: str
    status: str
    skills: list[str]
    created_at: str
    updated_at: str


class StaffListResponse(BaseModel):
    items: list[StaffResponse]
    total: int


def _get_staff_service() -> StaffService:
    return StaffService()


@router.post("", response_model=StaffResponse, status_code=status.HTTP_201_CREATED)
def create_staff(
    data: StaffCreateRequest,
    current_user: dict = Depends(get_current_user),
    service: StaffService = Depends(_get_staff_service),
) -> StaffResponse:
    """Create a new staff member."""
    result = service.create(name=data.name, role=data.role, skills=data.skills)
    if not result.success:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=result.error)
    s = result.data
    return StaffResponse(
        id=s.id,
        name=s.name,
        role=s.role,
        status=s.status,
        skills=s.skills or [],
        created_at=s.created_at.isoformat(),
        updated_at=s.updated_at.isoformat(),
    )


@router.get("", response_model=StaffListResponse)
def list_staff(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    current_user: dict = Depends(get_current_user),
    service: StaffService = Depends(_get_staff_service),
) -> StaffListResponse:
    """List active staff."""
    result = service.list_all()
    if not result.success:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=result.error)
    items = result.data or []
    return StaffListResponse(
        items=[
            StaffResponse(
                id=s.id,
                name=s.name,
                role=s.role,
                status=s.status,
                skills=s.skills or [],
                created_at=s.created_at.isoformat(),
                updated_at=s.updated_at.isoformat(),
            )
            for s in items
        ],
        total=len(items),
    )


@router.get("/{staff_id}", response_model=StaffResponse)
def get_staff(
    staff_id: UUID,
    current_user: dict = Depends(get_current_user),
    service: StaffService = Depends(_get_staff_service),
) -> StaffResponse:
    """Get staff by ID."""
    result = service.get(str(staff_id))
    if not result.success or result.data is None:
        raise HTTPException(status_code=404, detail="Staff not found")
    s = result.data
    return StaffResponse(
        id=s.id,
        name=s.name,
        role=s.role,
        status=s.status,
        skills=s.skills or [],
        created_at=s.created_at.isoformat(),
        updated_at=s.updated_at.isoformat(),
    )


@router.delete("/{staff_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_staff(
    staff_id: UUID,
    current_user: dict = Depends(get_current_user),
    service: StaffService = Depends(_get_staff_service),
) -> None:
    """Delete staff member."""
    result = service.delete(str(staff_id))
    if not result.success:
        raise HTTPException(status_code=404, detail="Staff not found")
