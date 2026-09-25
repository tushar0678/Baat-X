from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, EmailStr, Field

from app.models.enums import BusinessVertical, OrgRole


class CreateOrganizationRequest(BaseModel):
    name: str = Field(min_length=2, max_length=160)
    vertical: BusinessVertical = BusinessVertical.GENERIC
    country_code: str = Field(default="IN", min_length=2, max_length=2)
    timezone: str = Field(default="Asia/Kolkata", max_length=64)
    default_currency: str = Field(default="INR", min_length=3, max_length=3)


class OrganizationSummary(BaseModel):
    """One row in the organization switcher."""

    id: uuid.UUID
    name: str
    vertical: BusinessVertical
    role: OrgRole
    is_current: bool = False


class OrganizationResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    vertical: BusinessVertical
    country_code: str
    timezone: str
    default_currency: str
    role: OrgRole
    # Mirrored to the client only so it can hide buttons. The server decides
    # every actual request - the client list is never an authorization source.
    permissions: list[str] = Field(default_factory=list)

    @classmethod
    def from_model(
        cls, business, *, role: OrgRole, permissions: list[str] | None = None
    ) -> OrganizationResponse:  # noqa: ANN001
        return cls(
            id=business.id,
            name=business.name,
            vertical=BusinessVertical(business.vertical),
            country_code=business.country_code,
            timezone=business.timezone,
            default_currency=business.default_currency,
            role=role,
            permissions=permissions or [],
        )


class CreateTeamRequest(BaseModel):
    name: str = Field(min_length=2, max_length=120)
    description: str | None = Field(default=None, max_length=400)
    lead_user_id: uuid.UUID | None = None
    parent_team_id: uuid.UUID | None = None


class TeamResponse(BaseModel):
    id: uuid.UUID
    name: str
    description: str | None = None
    lead_user_id: uuid.UUID | None = None
    parent_team_id: uuid.UUID | None = None
    member_count: int = 0


class MemberResponse(BaseModel):
    user_id: uuid.UUID
    membership_id: uuid.UUID
    full_name: str
    email: str | None = None
    role: OrgRole
    team_id: uuid.UUID | None = None
    job_title: str | None = None


class UpdateMemberRequest(BaseModel):
    role: OrgRole | None = None
    team_id: uuid.UUID | None = None
    job_title: str | None = Field(default=None, max_length=80)
    # Owner-only. Revocations win over grants when both name the same thing.
    granted_permissions: list[str] | None = None
    revoked_permissions: list[str] | None = None


class InviteMemberRequest(BaseModel):
    email: EmailStr | None = None
    phone: str | None = Field(default=None, max_length=32)
    role: OrgRole = OrgRole.MEMBER
    team_id: uuid.UUID | None = None
    job_title: str | None = Field(default=None, max_length=80)


class InvitationResponse(BaseModel):
    id: uuid.UUID
    email: str | None = None
    phone: str | None = None
    role: OrgRole
    team_id: uuid.UUID | None = None
    status: str
    expires_at: datetime
    # Returned once, to whoever created the invite, so they can share the link.
    token: str | None = None

    @classmethod
    def from_model(cls, invitation, *, include_token: bool = True) -> InvitationResponse:  # noqa: ANN001
        return cls(
            id=invitation.id,
            email=invitation.email,
            phone=invitation.phone,
            role=OrgRole(invitation.role),
            team_id=invitation.team_id,
            status=invitation.status,
            expires_at=invitation.expires_at,
            token=invitation.token if include_token else None,
        )


class AcceptInvitationRequest(BaseModel):
    token: str = Field(min_length=16, max_length=64)
