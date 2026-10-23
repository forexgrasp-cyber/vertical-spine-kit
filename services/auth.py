"""Authentication service for vertical-spine-kit (SQLAlchemy-persisted, JWT-validated).

Storage: SQLite file by default (<slug>_auth.db), AUTH_DATABASE_URL or
DATABASE_URL overrides for production (e.g. PostgreSQL). Tables are
auto-created on import.

get_current_user performs REAL JWT validation: Bearer token -> signature +
expiry check -> user lookup in the database. Invalid/missing tokens get 401.
"""

from __future__ import annotations

import hashlib
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional
from uuid import uuid4

from fastapi import Depends, Header, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError, jwt
from sqlalchemy import Boolean, Column, DateTime, String, create_engine
from sqlalchemy.orm import declarative_base, sessionmaker

from services.license_service import LicenseInfo, LicenseService


def _license_svc() -> LicenseService:
    """Fresh LicenseService per call — picks up LICENSE_STORE_PATH env changes."""
    return LicenseService()

# Per-vertical auth database.
_DB_PATH = Path(__file__).resolve().parent.parent / "vertical-spine-kit_auth.db"
_DB_URL = (
    os.environ.get("AUTH_DATABASE_URL")
    or os.environ.get("DATABASE_URL")
    or f"sqlite:///{_DB_PATH.as_posix()}"
)
engine = create_engine(_DB_URL, echo=False)
_Base = declarative_base()

JWT_SECRET = os.environ.get("JWT_SECRET", "vertical-spine-kit-dev-jwt-secret-change-me")
JWT_ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 30
REFRESH_TOKEN_EXPIRE_DAYS = 30

_security = HTTPBearer(auto_error=False)


class UserORM(_Base):
    """Persisted user account."""

    __tablename__ = "auth_users"

    id = Column(String(36), primary_key=True)
    email = Column(String(255), nullable=False, unique=True, index=True)
    name = Column(String(255), nullable=False)
    company = Column(String(255), nullable=True)
    password_hash = Column(String(255), nullable=False)
    is_verified = Column(Boolean, nullable=False, default=False)
    is_active = Column(Boolean, nullable=False, default=True)
    created_at = Column(DateTime, nullable=False, default=lambda: datetime.now(timezone.utc))

    def to_dict(self) -> dict:
        return {
            "user_id": self.id,
            "email": self.email,
            "name": self.name,
            "company": self.company,
            "is_verified": self.is_verified,
        }


class RefreshTokenORM(_Base):
    """Persisted (revocable) refresh tokens."""

    __tablename__ = "auth_refresh_tokens"

    token = Column(String(512), primary_key=True)
    user_id = Column(String(36), nullable=False, index=True)
    email = Column(String(255), nullable=False)
    expires_at = Column(DateTime, nullable=False)


class VerificationTokenORM(_Base):
    """Persisted email-verification tokens."""

    __tablename__ = "auth_verification_tokens"

    token = Column(String(128), primary_key=True)
    user_id = Column(String(36), nullable=False, index=True)
    email = Column(String(255), nullable=False)
    expires_at = Column(DateTime, nullable=False)


_Base.metadata.create_all(engine)
_Session = sessionmaker(bind=engine, expire_on_commit=False)


def _hash_password(password: str) -> str:
    return hashlib.sha256(password.encode()).hexdigest()


class AuthService:
    """JWT-based authentication with SQLAlchemy persistence."""

    # ------------------------------------------------------------------
    # Token creation helpers
    # ------------------------------------------------------------------
    def _create_access_token(self, user_id: str, email: str) -> str:
        now = datetime.now(timezone.utc)
        expire = now + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
        return jwt.encode(
            {
                "sub": user_id,
                "email": email,
                "type": "access",
                "jti": str(uuid4()),
                "iat": int(now.timestamp()),
                "exp": int(expire.timestamp()),
            },
            JWT_SECRET,
            algorithm=JWT_ALGORITHM,
        )

    def _create_refresh_token(self, user_id: str, email: str) -> str:
        now = datetime.now(timezone.utc)
        expire = now + timedelta(days=REFRESH_TOKEN_EXPIRE_DAYS)
        token = jwt.encode(
            {
                "sub": user_id,
                "email": email,
                "type": "refresh",
                "jti": str(uuid4()),
                "iat": int(now.timestamp()),
                "exp": int(expire.timestamp()),
            },
            JWT_SECRET,
            algorithm=JWT_ALGORITHM,
        )
        with _Session() as session:
            session.add(
                RefreshTokenORM(
                    token=token,
                    user_id=user_id,
                    email=email,
                    expires_at=expire.replace(tzinfo=None),
                )
            )
            session.commit()
        return token

    # ------------------------------------------------------------------
    # Public API (same interface as the previous in-memory version)
    # ------------------------------------------------------------------
    async def register(
        self,
        email: str,
        password: str,
        name: str,
        company: Optional[str] = None,
    ) -> dict:
        email_lower = email.lower()
        user_id = str(uuid4())
        verification_token = _generate_token(32)

        try:
            with _Session() as session:
                if session.query(UserORM).filter(UserORM.email == email_lower).first():
                    raise HTTPException(
                        status_code=status.HTTP_400_BAD_REQUEST,
                        detail="Email already registered",
                    )
                session.add(
                    UserORM(
                        id=user_id,
                        email=email_lower,
                        name=name,
                        company=company,
                        password_hash=_hash_password(password),
                        is_verified=False,
                        is_active=True,
                    )
                )
                session.add(
                    VerificationTokenORM(
                        token=verification_token,
                        user_id=user_id,
                        email=email_lower,
                        expires_at=datetime.now(timezone.utc).replace(tzinfo=None) + timedelta(hours=24),
                    )
                )
                session.commit()
        except HTTPException:
            raise

        access_token = self._create_access_token(user_id, email_lower)
        refresh_token = self._create_refresh_token(user_id, email_lower)

        return {
            "access_token": access_token,
            "refresh_token": refresh_token,
            "token_type": "bearer",
            "verification_token": verification_token,
            "user_id": user_id,
            "user": {
                "user_id": user_id,
                "email": email_lower,
                "name": name,
                "company": company,
                "is_verified": False,
            },
        }

    async def login(self, email: str, password: str) -> dict:
        email_lower = email.lower()
        with _Session() as session:
            user = session.query(UserORM).filter(UserORM.email == email_lower).first()
            if not user or user.password_hash != _hash_password(password):
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="Invalid credentials",
                )
            if not user.is_active:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="Account is disabled",
                )
            user_id = user.id
            user_dict = user.to_dict()

        access_token = self._create_access_token(user_id, email_lower)
        refresh_token = self._create_refresh_token(user_id, email_lower)
        return {
            "access_token": access_token,
            "refresh_token": refresh_token,
            "token_type": "bearer",
            "user_id": user_id,
            "user": user_dict,
        }

    async def dev_login(self) -> dict:
        email = "dev@vertical-spine-kit.local"
        with _Session() as session:
            user = session.query(UserORM).filter(UserORM.email == email).first()
            if not user:
                user = UserORM(
                    id=str(uuid4()),
                    email=email,
                    name="Dev User",
                    company="Vertical Spine Kit",
                    password_hash=_hash_password("devpassword"),
                    is_verified=True,
                    is_active=True,
                )
                session.add(user)
                session.commit()
            user_id = user.id
            user_dict = user.to_dict()

        access_token = self._create_access_token(user_id, email)
        refresh_token = self._create_refresh_token(user_id, email)
        return {
            "access_token": access_token,
            "refresh_token": refresh_token,
            "token_type": "bearer",
            "user_id": user_id,
            "user": user_dict,
        }

    async def verify_email(self, token: str) -> dict:
        with _Session() as session:
            record = session.get(VerificationTokenORM, token)
            if not record:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Invalid or expired verification token",
                )
            if record.expires_at < datetime.utcnow():
                session.delete(record)
                session.commit()
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Verification token has expired",
                )
            user = session.query(UserORM).filter(UserORM.email == record.email).first()
            if not user:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="User not found",
                )
            user.is_verified = True
            session.delete(record)
            session.commit()
        return {"status": "verified", "message": "Email successfully verified"}

    async def refresh_token(self, refresh_token: str) -> dict:
        try:
            payload = jwt.decode(refresh_token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
        except JWTError:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid refresh token",
            )
        if payload.get("type") != "refresh":
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid token type",
            )

        with _Session() as session:
            record = session.get(RefreshTokenORM, refresh_token)
            if not record:
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="Refresh token revoked",
                )
            if record.expires_at < datetime.utcnow():
                session.delete(record)
                session.commit()
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="Refresh token expired",
                )
            user_id = record.user_id
            email = record.email
            # Rotate: revoke old, issue new
            session.delete(record)
            session.commit()

        new_access = self._create_access_token(user_id, email)
        new_refresh = self._create_refresh_token(user_id, email)

        with _Session() as session:
            user = session.query(UserORM).filter(UserORM.email == email).first()
            user_dict = user.to_dict() if user else {}

        return {
            "access_token": new_access,
            "refresh_token": new_refresh,
            "token_type": "bearer",
            "user_id": user_id,
            "user": user_dict,
        }

    async def logout(self, user_id: str) -> None:
        """Revoke all refresh tokens for the user."""
        with _Session() as session:
            session.query(RefreshTokenORM).filter(
                RefreshTokenORM.user_id == str(user_id)
            ).delete()
            session.commit()

    async def get_user_by_id(self, user_id: str) -> Optional[dict]:
        with _Session() as session:
            user = session.get(UserORM, str(user_id))
            return user.to_dict() if user else None

    # ------------------------------------------------------------------
    # JWT validation (sync internals, used by the dependency below)
    # ------------------------------------------------------------------
    def _validate_access_token(self, token: str) -> dict:
        """Validate a JWT access token and return the user dict.

        Raises 401 on: bad signature, expiry, wrong type, unknown user,
        or disabled account.
        """
        try:
            payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
        except JWTError:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid or expired token",
                headers={"WWW-Authenticate": "Bearer"},
            )
        if payload.get("type") != "access":
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid token type",
                headers={"WWW-Authenticate": "Bearer"},
            )
        user_id = payload.get("sub")
        with _Session() as session:
            user = session.get(UserORM, str(user_id)) if user_id else None
            if not user or not user.is_active:
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="User not found or disabled",
                    headers={"WWW-Authenticate": "Bearer"},
                )
            return user.to_dict()


def _generate_token(length: int = 32) -> str:
    import secrets

    return secrets.token_urlsafe(length)


_auth_service_instance: Optional[AuthService] = None


def get_auth_service() -> AuthService:
    global _auth_service_instance
    if _auth_service_instance is None:
        _auth_service_instance = AuthService()
    return _auth_service_instance


async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(_security),
) -> dict:
    """FastAPI dependency: validate the Bearer token and load the user.

    Raises 401 when the Authorization header is missing, the JWT is
    invalid/expired, or the user no longer exists.
    """
    if credentials is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return get_auth_service()._validate_access_token(credentials.credentials)


def get_current_license(
    x_license_key: str | None = Header(default=None, alias="X-License-Key"),
) -> LicenseInfo | None:
    """FastAPI dependency: validate the X-License-Key header.

    Returns the LicenseInfo when a valid key is provided, or None when no
    header is sent. Invalid keys raise 401.
    """
    if not x_license_key:
        return None
    try:
        return _license_svc().verify_revoked(x_license_key)
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or revoked license key",
            headers={"WWW-Authenticate": "License"},
        )


def require_license(
    license: LicenseInfo | None = Depends(get_current_license),
) -> LicenseInfo:
    """FastAPI dependency: require a valid license key.

    Raises 401 when no X-License-Key header is present or the key is
    invalid/revoked.
    """
    if license is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Valid license key required (X-License-Key header)",
            headers={"WWW-Authenticate": "License"},
        )
    return license