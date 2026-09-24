from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, EmailStr, Field

from app.models.enums import BusinessVertical, Role


class SignupRequest(BaseModel):
    full_name: str = Field(min_length=2, max_length=160)
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)
    phone: str | None = Field(default=None, max_length=32)
    business_name: str = Field(min_length=2, max_length=160)
    vertical: BusinessVertical = BusinessVertical.GENERIC
    timezone: str = "Asia/Kolkata"
    currency: str = Field(default="INR", min_length=3, max_length=3)


class LoginRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=1, max_length=128)
    business_id: uuid.UUID | None = None


class RefreshRequest(BaseModel):
    refresh_token: str


class BusinessSummary(BaseModel):
    id: uuid.UUID
    name: str
    vertical: BusinessVertical
    role: Role
    currency: str
    timezone: str


class UserProfile(BaseModel):
    id: uuid.UUID
    full_name: str
    email: EmailStr
    phone: str | None
    locale: str
    businesses: list[BusinessSummary]


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_at: datetime
    user: UserProfile
    active_business_id: uuid.UUID | None = None


class InviteMemberRequest(BaseModel):
    email: EmailStr
    full_name: str = Field(min_length=2, max_length=160)
    role: Role = Role.SALESPERSON
    temporary_password: str = Field(min_length=8, max_length=128)


class MemberResponse(BaseModel):
    user_id: uuid.UUID
    full_name: str
    email: EmailStr
    role: Role
    is_active: bool
