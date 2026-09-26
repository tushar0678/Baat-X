from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Request, status
from sqlalchemy import select

from app.auth.deps import CurrentUser, CurrentUserDep, DbDep, requires
from app.auth.security import create_token, decode_token, hash_password, verify_password
from app.core.errors import AuthenticationError, ConflictError
from app.models.billing import Subscription
from app.models.enums import Role, SubscriptionPlan
from app.models.tenancy import Business, BusinessMembership, User
from app.repositories.audit_repo import AuditRepository
from app.schemas.auth import (
    BusinessSummary,
    InviteMemberRequest,
    LoginRequest,
    MemberResponse,
    RefreshRequest,
    SignupRequest,
    TokenResponse,
    UserProfile,
)

router = APIRouter(prefix="/auth", tags=["Auth"])


async def _profile(db, user: User) -> UserProfile:  # noqa: ANN001
    rows = (
        await db.execute(
            select(BusinessMembership, Business)
            .join(Business, Business.id == BusinessMembership.business_id)
            .where(BusinessMembership.user_id == user.id)
            .where(BusinessMembership.is_active.is_(True))
        )
    ).all()
    return UserProfile(
        id=user.id,
        full_name=user.full_name,
        email=user.email,
        phone=user.phone,
        locale=user.locale,
        businesses=[
            BusinessSummary(
                id=business.id,
                name=business.name,
                vertical=business.vertical,
                role=Role(membership.role),
                currency=business.default_currency,
                timezone=business.timezone,
            )
            for membership, business in rows
        ],
    )


def _tokens(
    user: User, business_id: uuid.UUID | None, role: Role | None
) -> tuple[str, str, datetime]:
    access, expires_at = create_token(
        user_id=user.id,
        token_type="access",
        business_id=business_id,
        role=role.value if role else None,
        token_version=user.token_version,
    )
    refresh, _ = create_token(
        user_id=user.id,
        token_type="refresh",
        business_id=business_id,
        token_version=user.token_version,
    )
    return access, refresh, expires_at


@router.post("/signup", response_model=TokenResponse, status_code=status.HTTP_201_CREATED)
async def signup(db: DbDep, payload: SignupRequest) -> TokenResponse:
    """Creates the user, their business and an OWNER membership in one step."""
    existing = (
        await db.execute(select(User).where(User.email == payload.email.lower()))
    ).scalar_one_or_none()
    if existing is not None:
        raise ConflictError(
            "email exists", user_message="An account with this email already exists."
        )

    user = User(
        email=payload.email.lower(),
        full_name=payload.full_name,
        phone=payload.phone,
        password_hash=hash_password(payload.password),
    )
    business = Business(
        name=payload.business_name,
        vertical=payload.vertical,
        timezone=payload.timezone,
        default_currency=payload.currency.upper(),
        is_active=True,
        whatsapp_enabled=False,
    )
    db.add_all([user, business])
    await db.flush()
    db.add_all(
        [
            BusinessMembership(user_id=user.id, business_id=business.id, role=Role.OWNER),
            Subscription(
                    business_id=business.id,
                    plan=SubscriptionPlan.FREE,
                    is_active=True,
                    seats=1,
                    monthly_minutes_quota=300,
                    monthly_ai_requests_quota=100,
                ),
        ]
    )
    await db.flush()

    access, refresh, expires_at = _tokens(user, business.id, Role.OWNER)
    return TokenResponse(
        access_token=access,
        refresh_token=refresh,
        expires_at=expires_at,
        user=await _profile(db, user),
        active_business_id=business.id,
    )


@router.post("/login", response_model=TokenResponse)
async def login(request: Request, db: DbDep, payload: LoginRequest) -> TokenResponse:
    user = (
        await db.execute(select(User).where(User.email == payload.email.lower()))
    ).scalar_one_or_none()
    # Identical failure for unknown email and wrong password - no user enumeration.
    if (
        user is None
        or not user.is_active
        or not verify_password(payload.password, user.password_hash)
    ):
        raise AuthenticationError("bad credentials", user_message="Incorrect email or password.")

    memberships = (
        await db.execute(
            select(BusinessMembership)
            .where(BusinessMembership.user_id == user.id)
            .where(BusinessMembership.is_active.is_(True))
        )
    ).scalars().all()
    membership = next(
        (m for m in memberships if payload.business_id and m.business_id == payload.business_id),
        memberships[0] if memberships else None,
    )

    user.last_login_at = datetime.now(UTC)
    if membership is not None:
        await AuditRepository(db, membership.business_id).record(
            action="auth.login",
            actor_user_id=user.id,
            request_id=getattr(request.state, "request_id", None),
            ip_address=request.client.host if request.client else None,
        )

    access, refresh, expires_at = _tokens(
        user,
        membership.business_id if membership else None,
        Role(membership.role) if membership else None,
    )
    return TokenResponse(
        access_token=access,
        refresh_token=refresh,
        expires_at=expires_at,
        user=await _profile(db, user),
        active_business_id=membership.business_id if membership else None,
    )


@router.post("/refresh", response_model=TokenResponse)
async def refresh_token(db: DbDep, payload: RefreshRequest) -> TokenResponse:
    claims = decode_token(payload.refresh_token, "refresh")
    user = await db.get(User, claims.user_id)
    if user is None or not user.is_active or user.token_version != claims.token_version:
        raise AuthenticationError("refresh rejected")

    role: Role | None = None
    if claims.business_id:
        membership = (
            await db.execute(
                select(BusinessMembership)
                .where(BusinessMembership.user_id == user.id)
                .where(BusinessMembership.business_id == claims.business_id)
                .where(BusinessMembership.is_active.is_(True))
            )
        ).scalar_one_or_none()
        role = Role(membership.role) if membership else None

    access, refresh, expires_at = _tokens(user, claims.business_id, role)
    return TokenResponse(
        access_token=access,
        refresh_token=refresh,
        expires_at=expires_at,
        user=await _profile(db, user),
        active_business_id=claims.business_id,
    )


@router.post("/logout-all", status_code=status.HTTP_204_NO_CONTENT)
async def logout_all(db: DbDep, principal: CurrentUserDep) -> None:
    """Invalidates every issued token for this user."""
    principal.user.token_version += 1
    await db.flush()


@router.get("/me", response_model=UserProfile)
async def me(db: DbDep, principal: CurrentUserDep) -> UserProfile:
    return await _profile(db, principal.user)


@router.get("/team", response_model=list[MemberResponse])
async def team(
    db: DbDep, principal: Annotated[CurrentUser, requires("team:read")]
) -> list[MemberResponse]:
    rows = (
        await db.execute(
            select(BusinessMembership, User)
            .join(User, User.id == BusinessMembership.user_id)
            .where(BusinessMembership.business_id == principal.business_id)
        )
    ).all()
    return [
        MemberResponse(
            user_id=user.id,
            full_name=user.full_name,
            email=user.email,
            role=Role(membership.role),
            is_active=membership.is_active,
        )
        for membership, user in rows
    ]


@router.post("/team", response_model=MemberResponse, status_code=status.HTTP_201_CREATED)
async def invite_member(
    db: DbDep,
    principal: Annotated[CurrentUser, requires("team:write")],
    payload: InviteMemberRequest,
) -> MemberResponse:
    user = (
        await db.execute(select(User).where(User.email == payload.email.lower()))
    ).scalar_one_or_none()
    if user is None:
        user = User(
            email=payload.email.lower(),
            full_name=payload.full_name,
            password_hash=hash_password(payload.temporary_password),
        )
        db.add(user)
        await db.flush()

    existing = (
        await db.execute(
            select(BusinessMembership)
            .where(BusinessMembership.user_id == user.id)
            .where(BusinessMembership.business_id == principal.business_id)
        )
    ).scalar_one_or_none()
    if existing is not None:
        raise ConflictError(
            "already a member", user_message="This person is already on your team."
        )

    db.add(
        BusinessMembership(
            user_id=user.id, business_id=principal.business_id, role=payload.role
        )
    )
    await db.flush()
    return MemberResponse(
        user_id=user.id,
        full_name=user.full_name,
        email=user.email,
        role=payload.role,
        is_active=True,
    )
