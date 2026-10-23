"""Authentication routes for vertical-spine-kit."""

from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, status
from pydantic import BaseModel, EmailStr, Field

from services.auth import AuthService, get_auth_service, get_current_user

# No prefix here - main.py mounts with prefix="/api/auth"
router = APIRouter(tags=["Authentication"])


class RegisterRequest(BaseModel):
    email: EmailStr
    password: str = Field(..., min_length=8, max_length=128)
    name: str = Field(..., min_length=1, max_length=255)
    company: Optional[str] = Field(None, max_length=255)


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class VerifyEmailRequest(BaseModel):
    token: str


class RefreshTokenRequest(BaseModel):
    refresh_token: str


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    verification_token: Optional[str] = None
    user_id: Optional[str] = None
    user: dict


class DevLoginResponse(BaseModel):
    access_token: str
    refresh_token: str = ""
    token_type: str = "bearer"
    user_id: Optional[str] = None
    user: dict


@router.post("/register", response_model=TokenResponse, status_code=status.HTTP_201_CREATED)
async def register(
    data: RegisterRequest,
    service: AuthService = Depends(get_auth_service),
) -> TokenResponse:
    """Register a new user. Returns tokens + verification_token + user_id."""
    result = await service.register(
        email=data.email,
        password=data.password,
        name=data.name,
        company=data.company,
    )
    return TokenResponse(**result)


@router.post("/login", response_model=TokenResponse)
async def login(
    data: LoginRequest,
    service: AuthService = Depends(get_auth_service),
) -> TokenResponse:
    """Login with email and password."""
    result = await service.login(data.email, data.password)
    return TokenResponse(**result)


@router.post("/dev-login", response_model=DevLoginResponse)
async def dev_login(
    service: AuthService = Depends(get_auth_service),
) -> DevLoginResponse:
    """Development login - creates/returns a test user."""
    result = await service.dev_login()
    return DevLoginResponse(**result)


@router.post("/verify-email")
async def verify_email(
    data: VerifyEmailRequest,
    service: AuthService = Depends(get_auth_service),
) -> dict:
    """Verify email with token (JSON body)."""
    return await service.verify_email(data.token)


@router.post("/refresh", response_model=TokenResponse)
async def refresh_token(
    data: RefreshTokenRequest,
    service: AuthService = Depends(get_auth_service),
) -> TokenResponse:
    """Refresh access token (JSON body)."""
    result = await service.refresh_token(data.refresh_token)
    return TokenResponse(**result)


@router.post("/logout")
async def logout(
    current_user: dict = Depends(get_current_user),
    service: AuthService = Depends(get_auth_service),
) -> dict:
    """Logout current user - revokes refresh tokens."""
    await service.logout(current_user.get("user_id", ""))
    return {"status": "logged_out"}


@router.get("/me")
async def get_me(
    current_user: dict = Depends(get_current_user),
) -> dict:
    """Get current user info."""
    return current_user
