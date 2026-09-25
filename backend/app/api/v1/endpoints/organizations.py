"""Organizations, teams, members and invitations."""

from __future__ import annotations

import secrets
import uuid
from datetime import UTC, datetime, timedelta
from typing import Annotated

from fastapi import APIRouter, Request, status
from sqlalchemy import func, select
from sqlalchemy.orm import selectinload

from app.auth.deps import CurrentUser, CurrentUserDep, DbDep, requires
from app.auth.permissions import effective_permissions
from app.auth.rbac import VisibilityScope
from app.core.errors import ConflictError, NotFoundError, ValidationError
from app.models.enums import OrgRole
from app.models.tenancy import Business, BusinessMembership, Invitation, Team, User
from app.repositories.audit_repo import AuditRepository
from app.schemas.organization import (
    AcceptInvitationRequest,
    CreateOrganizationRequest,
    CreateTeamRequest,
    InvitationResponse,
    InviteMemberRequest,
    MemberResponse,
    OrganizationResponse,
    OrganizationSummary,
    TeamResponse,
    UpdateMemberRequest,
)

router = APIRouter(prefix="/organizations", tags=["Organizations"])

INVITE_TTL_DAYS = 14


@router.get("", response_model=list[OrganizationSummary], summary="Organizations I belong to")
async def my_organizations(db: DbDep, principal: CurrentUserDep) -> list[OrganizationSummary]:
    """Powers the organization switcher. Only active memberships are listed."""
    result = await db.execute(
        select(BusinessMembership)
        .options(selectinload(BusinessMembership.business))
        .where(
            BusinessMembership.user_id == principal.user_id,
            BusinessMembership.is_active.is_(True),
        )
    )
    return [
        OrganizationSummary(
            id=m.business.id,
            name=m.business.name,
            vertical=m.business.vertical,
            role=OrgRole(m.role),
            is_current=m.business_id == principal.business_id,
        )
        for m in result.scalars().all()
        if m.business.is_active
    ]


@router.post(
    "",
    response_model=OrganizationResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create an organization",
)
async def create_organization(
    request: Request,
    db: DbDep,
    principal: CurrentUserDep,
    payload: CreateOrganizationRequest,
) -> OrganizationResponse:
    """Anyone may start an organization; the creator becomes its owner.

    No permission gate here on purpose - this creates a brand new tenant and
    touches no existing one.
    """
    business = Business(
        name=payload.name.strip(),
        vertical=payload.vertical,
        country_code=payload.country_code.upper(),
        timezone=payload.timezone,
        default_currency=payload.default_currency.upper(),
        created_by_user_id=principal.user_id,
    )
    db.add(business)
    await db.flush()

    db.add(
        BusinessMembership(
            business_id=business.id,
            user_id=principal.user_id,
            role=OrgRole.OWNER,
            job_title="Owner",
        )
    )
    await db.flush()

    await AuditRepository(db, business.id).record(
        action="org.created",
        actor_user_id=principal.user_id,
        entity_type="business",
        entity_id=business.id,
        request_id=getattr(request.state, "request_id", None),
    )
    await db.commit()

    return OrganizationResponse.from_model(
        business,
        role=OrgRole.OWNER,
        permissions=sorted(str(p) for p in effective_permissions(OrgRole.OWNER)),
    )


@router.get("/current", response_model=OrganizationResponse, summary="Active organization")
async def current_organization(principal: CurrentUserDep) -> OrganizationResponse:
    return OrganizationResponse.from_model(
        principal.business,
        role=principal.role,
        permissions=sorted(str(p) for p in principal.permissions),
    )


# ---------------------------------------------------------------- teams


@router.get("/teams", response_model=list[TeamResponse], summary="Teams in this organization")
async def list_teams(
    db: DbDep,
    principal: Annotated[CurrentUser, requires("customer:read")],
) -> list[TeamResponse]:
    """Team names alone reveal how a business is structured, so the same
    visibility rules that govern CRM rows govern this list."""
    scope = principal.scope()

    stmt = select(Team).where(Team.business_id == principal.business_id, Team.is_active.is_(True))

    if scope.scope is VisibilityScope.TEAM and scope.team_ids:
        stmt = stmt.where(Team.id.in_(scope.team_ids))
    elif scope.scope is VisibilityScope.OWN:
        if principal.team_id is None:
            return []
        stmt = stmt.where(Team.id == principal.team_id)

    teams = (await db.execute(stmt.order_by(Team.name))).scalars().all()

    counts = dict(
        (
            await db.execute(
                select(BusinessMembership.team_id, func.count())
                .where(
                    BusinessMembership.business_id == principal.business_id,
                    BusinessMembership.is_active.is_(True),
                )
                .group_by(BusinessMembership.team_id)
            )
        ).all()
    )

    return [
        TeamResponse(
            id=t.id,
            name=t.name,
            description=t.description,
            lead_user_id=t.lead_user_id,
            parent_team_id=t.parent_team_id,
            member_count=counts.get(t.id, 0),
        )
        for t in teams
    ]


@router.post(
    "/teams",
    response_model=TeamResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a team",
)
async def create_team(
    request: Request,
    db: DbDep,
    principal: Annotated[CurrentUser, requires("team:manage")],
    payload: CreateTeamRequest,
) -> TeamResponse:
    existing = await db.execute(
        select(Team).where(
            Team.business_id == principal.business_id,
            func.lower(Team.name) == payload.name.strip().lower(),
        )
    )
    if existing.scalar_one_or_none() is not None:
        raise ConflictError("team exists", user_message="A team with this name already exists.")

    if payload.parent_team_id is not None:
        # Confined to this organization, so a parent id cannot graft a foreign
        # team into our hierarchy - and with it, another tenant's members.
        parent = await db.get(Team, payload.parent_team_id)
        if parent is None or parent.business_id != principal.business_id:
            raise ValidationError("invalid parent team")

    team = Team(
        business_id=principal.business_id,
        name=payload.name.strip(),
        description=payload.description,
        lead_user_id=payload.lead_user_id,
        parent_team_id=payload.parent_team_id,
    )
    db.add(team)
    await db.flush()

    if payload.lead_user_id is not None:
        membership = await _require_member(db, principal.business_id, payload.lead_user_id)
        membership.team_id = team.id
        # Leading a team implies the role, unless the person is already senior.
        if OrgRole(membership.role) == OrgRole.MEMBER:
            membership.role = OrgRole.TEAM_LEAD

    await AuditRepository(db, principal.business_id).record(
        action="team.created",
        actor_user_id=principal.user_id,
        entity_type="team",
        entity_id=team.id,
        request_id=getattr(request.state, "request_id", None),
        metadata={"has_lead": payload.lead_user_id is not None},
    )
    await db.commit()

    return TeamResponse(
        id=team.id,
        name=team.name,
        description=team.description,
        lead_user_id=team.lead_user_id,
        parent_team_id=team.parent_team_id,
        member_count=1 if payload.lead_user_id else 0,
    )


# ---------------------------------------------------------------- members


@router.get("/members", response_model=list[MemberResponse], summary="People in this organization")
async def list_members(
    db: DbDep,
    principal: Annotated[CurrentUser, requires("customer:read")],
) -> list[MemberResponse]:
    scope = principal.scope()

    stmt = (
        select(BusinessMembership, User)
        .join(User, User.id == BusinessMembership.user_id)
        .where(
            BusinessMembership.business_id == principal.business_id,
            BusinessMembership.is_active.is_(True),
        )
    )

    if not scope.unrestricted:
        stmt = stmt.where(BusinessMembership.user_id.in_(scope.user_ids or {principal.user_id}))

    rows = (await db.execute(stmt.order_by(User.full_name))).all()
    return [
        MemberResponse(
            user_id=user.id,
            membership_id=membership.id,
            full_name=user.full_name,
            email=user.email,
            role=OrgRole(membership.role),
            team_id=membership.team_id,
            job_title=membership.job_title,
        )
        for membership, user in rows
    ]


@router.patch(
    "/members/{membership_id}",
    response_model=MemberResponse,
    summary="Change a member's role, team or permissions",
)
async def update_member(
    request: Request,
    db: DbDep,
    principal: Annotated[CurrentUser, requires("user:manage")],
    membership_id: uuid.UUID,
    payload: UpdateMemberRequest,
) -> MemberResponse:
    membership = await db.get(BusinessMembership, membership_id)
    if membership is None or membership.business_id != principal.business_id:
        raise NotFoundError("member not found")

    if membership.user_id == principal.user_id and payload.role is not None:
        # Stops an owner demoting themselves and stranding the organization
        # with nobody able to administer it.
        raise ValidationError(
            "cannot change own role",
            user_message="You can't change your own role. Ask another manager.",
        )

    if payload.role == OrgRole.OWNER:
        principal.require("org:manage")

    if payload.team_id is not None:
        team = await db.get(Team, payload.team_id)
        if team is None or team.business_id != principal.business_id:
            raise ValidationError("invalid team")
        membership.team_id = payload.team_id

    if payload.role is not None:
        membership.role = payload.role
    if payload.job_title is not None:
        membership.job_title = payload.job_title

    # Only an owner hands out bespoke permissions.
    if payload.granted_permissions is not None or payload.revoked_permissions is not None:
        principal.require("permission:manage")
        if payload.granted_permissions is not None:
            membership.granted_permissions = payload.granted_permissions
        if payload.revoked_permissions is not None:
            membership.revoked_permissions = payload.revoked_permissions

    await AuditRepository(db, principal.business_id).record(
        action="member.updated",
        actor_user_id=principal.user_id,
        entity_type="business_membership",
        entity_id=membership.id,
        request_id=getattr(request.state, "request_id", None),
        metadata={
            "role_changed": payload.role is not None,
            "team_changed": payload.team_id is not None,
            "permissions_changed": payload.granted_permissions is not None
            or payload.revoked_permissions is not None,
        },
    )
    await db.commit()

    user = await db.get(User, membership.user_id)
    return MemberResponse(
        user_id=membership.user_id,
        membership_id=membership.id,
        full_name=user.full_name if user else "",
        email=user.email if user else None,
        role=OrgRole(membership.role),
        team_id=membership.team_id,
        job_title=membership.job_title,
    )


@router.delete(
    "/members/{membership_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Remove someone from this organization",
)
async def remove_member(
    request: Request,
    db: DbDep,
    principal: Annotated[CurrentUser, requires("user:manage")],
    membership_id: uuid.UUID,
) -> None:
    membership = await db.get(BusinessMembership, membership_id)
    if membership is None or membership.business_id != principal.business_id:
        raise NotFoundError("member not found")

    if membership.user_id == principal.user_id:
        raise ValidationError(
            "cannot remove self",
            user_message="You can't remove yourself from your own organization.",
        )

    if OrgRole(membership.role) == OrgRole.OWNER:
        principal.require("org:manage")

    # Deactivated rather than deleted: the CRM records this person created stay
    # attributed to them and the audit trail stays intact, while access stops
    # on the very next request.
    membership.is_active = False

    await AuditRepository(db, principal.business_id).record(
        action="member.removed",
        actor_user_id=principal.user_id,
        entity_type="business_membership",
        entity_id=membership.id,
        request_id=getattr(request.state, "request_id", None),
    )
    await db.commit()


# ---------------------------------------------------------------- invitations


@router.post(
    "/invitations",
    response_model=InvitationResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Invite someone to this organization",
)
async def invite_member(
    request: Request,
    db: DbDep,
    principal: Annotated[CurrentUser, requires("user:manage")],
    payload: InviteMemberRequest,
) -> InvitationResponse:
    if not payload.email and not payload.phone:
        raise ValidationError(
            "contact required", user_message="Enter an email address or phone number."
        )

    if payload.role == OrgRole.OWNER:
        principal.require("org:manage")

    if payload.team_id is not None:
        team = await db.get(Team, payload.team_id)
        if team is None or team.business_id != principal.business_id:
            raise ValidationError("invalid team")

    invitation = Invitation(
        business_id=principal.business_id,
        email=payload.email.lower().strip() if payload.email else None,
        phone=payload.phone.strip() if payload.phone else None,
        role=payload.role,
        team_id=payload.team_id,
        job_title=payload.job_title,
        token=secrets.token_urlsafe(32),
        expires_at=datetime.now(UTC) + timedelta(days=INVITE_TTL_DAYS),
        invited_by_user_id=principal.user_id,
    )
    db.add(invitation)
    await db.flush()

    await AuditRepository(db, principal.business_id).record(
        action="invitation.sent",
        actor_user_id=principal.user_id,
        entity_type="invitation",
        entity_id=invitation.id,
        request_id=getattr(request.state, "request_id", None),
        # Role and outcome only - the invitee's contact details stay out of logs.
        metadata={"role": payload.role.value},
    )
    await db.commit()

    return InvitationResponse.from_model(invitation)


@router.post("/invitations/accept", response_model=OrganizationResponse, summary="Accept an invite")
async def accept_invitation(
    request: Request,
    db: DbDep,
    principal: CurrentUserDep,
    payload: AcceptInvitationRequest,
) -> OrganizationResponse:
    result = await db.execute(select(Invitation).where(Invitation.token == payload.token))
    invitation = result.scalar_one_or_none()

    if invitation is None or invitation.status != "pending":
        raise NotFoundError(
            "invitation not found", user_message="This invitation is no longer valid."
        )

    if invitation.expires_at < datetime.now(UTC):
        invitation.status = "expired"
        await db.commit()
        raise ValidationError(
            "invitation expired",
            user_message="This invitation has expired. Please ask for a new one.",
        )

    existing = await db.execute(
        select(BusinessMembership).where(
            BusinessMembership.business_id == invitation.business_id,
            BusinessMembership.user_id == principal.user_id,
        )
    )
    membership = existing.scalar_one_or_none()

    if membership is not None:
        # Re-joining after removal reuses the row, so history is preserved.
        membership.is_active = True
        membership.role = invitation.role
        membership.team_id = invitation.team_id
    else:
        db.add(
            BusinessMembership(
                business_id=invitation.business_id,
                user_id=principal.user_id,
                role=invitation.role,
                team_id=invitation.team_id,
                job_title=invitation.job_title,
            )
        )

    invitation.status = "accepted"
    invitation.accepted_by_user_id = principal.user_id
    invitation.accepted_at = datetime.now(UTC)

    await AuditRepository(db, invitation.business_id).record(
        action="invitation.accepted",
        actor_user_id=principal.user_id,
        entity_type="invitation",
        entity_id=invitation.id,
        request_id=getattr(request.state, "request_id", None),
    )
    await db.commit()

    business = await db.get(Business, invitation.business_id)
    role = OrgRole(invitation.role)
    return OrganizationResponse.from_model(
        business,
        role=role,
        permissions=sorted(str(p) for p in effective_permissions(role)),
    )


async def _require_member(
    db,  # noqa: ANN001
    business_id: uuid.UUID,
    user_id: uuid.UUID,
) -> BusinessMembership:
    result = await db.execute(
        select(BusinessMembership).where(
            BusinessMembership.business_id == business_id,
            BusinessMembership.user_id == user_id,
            BusinessMembership.is_active.is_(True),
        )
    )
    membership = result.scalar_one_or_none()
    if membership is None:
        raise ValidationError(
            "not a member", user_message="That person isn't a member of this organization."
        )
    return membership
