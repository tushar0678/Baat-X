"""Request authorization: who is this, which organization, and what may they see.

Every protected endpoint depends on :class:`CurrentUser`, assembled here from
the access token *and* a live database lookup. The organization is resolved
from the token or the ``X-Organization-Id`` header and then re-verified against
an active membership - a client-supplied organization id is never trusted, and
a revoked membership stops working on the very next request rather than at
token expiry.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from typing import Annotated

from fastapi import Depends, Header, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.auth.permissions import Permission, effective_permissions
from app.auth.rbac import ScopeFilter, scope_filter
from app.auth.security import decode_token
from app.core.errors import AuthenticationError, AuthorizationError
from app.db.session import get_session
from app.models.enums import OrgRole
from app.models.tenancy import Business, BusinessMembership, Team, User

DbDep = Annotated[AsyncSession, Depends(get_session)]


@dataclass(slots=True)
class CurrentUser:
    """The authenticated principal, bound to exactly one organization."""

    user_id: uuid.UUID
    user: User
    business_id: uuid.UUID
    business: Business
    membership_id: uuid.UUID
    role: OrgRole
    team_id: uuid.UUID | None
    permissions: frozenset[Permission]

    # Resolved lazily: only requests that read CRM rows need the team walk.
    _team_ids: set[uuid.UUID] = field(default_factory=set)
    _teammate_ids: set[uuid.UUID] = field(default_factory=set)
    _visibility_loaded: bool = False

    def has(self, permission: Permission | str) -> bool:
        return _coerce(permission) in self.permissions

    def require(self, permission: Permission | str) -> None:
        if not self.has(permission):
            raise AuthorizationError(
                f"missing permission: {permission}",
                user_message="You don't have access to do this.",
            )

    def scope(self) -> ScopeFilter:
        """The row filter for this request. Pass into repositories/services."""
        return scope_filter(
            self.role,
            self.user_id,
            team_ids=self._team_ids,
            teammate_user_ids=self._teammate_ids,
        )

    async def load_visibility(self, session: AsyncSession) -> None:
        """Resolve the team subtree and its members. Idempotent per request."""
        if self._visibility_loaded or self.team_id is None:
            self._visibility_loaded = True
            return

        self._team_ids = await _team_subtree(
            session, business_id=self.business_id, root_team_id=self.team_id
        )

        if self._team_ids:
            result = await session.execute(
                select(BusinessMembership.user_id).where(
                    BusinessMembership.business_id == self.business_id,
                    BusinessMembership.team_id.in_(self._team_ids),
                    BusinessMembership.is_active.is_(True),
                )
            )
            self._teammate_ids = {row[0] for row in result.all()}

        self._visibility_loaded = True


def _coerce(permission: Permission | str) -> Permission | str:
    """Accept both ``Permission.CUSTOMER_READ`` and ``"customer:read"``.

    Endpoints were written with plain strings; new code uses the enum. Both
    resolve to the same member, so neither style has to be rewritten.
    """
    if isinstance(permission, Permission):
        return permission
    try:
        return Permission(permission)
    except ValueError:
        return permission


async def _team_subtree(
    session: AsyncSession, *, business_id: uuid.UUID, root_team_id: uuid.UUID
) -> set[uuid.UUID]:
    """A team plus every team nested beneath it.

    Breadth-first with a visited set, so bad data that parents two teams to
    each other cannot hang the request. Confined to one ``business_id``, so a
    mis-parented team elsewhere can never pull foreign teams into scope.
    """
    found: set[uuid.UUID] = {root_team_id}
    frontier: list[uuid.UUID] = [root_team_id]

    while frontier:
        result = await session.execute(
            select(Team.id).where(
                Team.business_id == business_id,
                Team.parent_team_id.in_(frontier),
                Team.is_active.is_(True),
            )
        )
        children = {row[0] for row in result.all()} - found
        if not children:
            break
        found |= children
        frontier = list(children)

    return found


async def _resolve_membership(
    session: AsyncSession, *, user_id: uuid.UUID, business_id: uuid.UUID
) -> BusinessMembership:
    """Load an active membership, or refuse.

    The single gate into a tenant, re-checked on every request so that removing
    someone takes effect at once.
    """
    result = await session.execute(
        select(BusinessMembership)
        .options(selectinload(BusinessMembership.business))
        .where(
            BusinessMembership.user_id == user_id,
            BusinessMembership.business_id == business_id,
            BusinessMembership.is_active.is_(True),
        )
    )
    membership = result.scalar_one_or_none()

    if membership is None or not membership.business.is_active:
        # Deliberately indistinguishable from "no such organization": probing
        # for valid organization ids should reveal nothing.
        raise AuthorizationError(
            "no active membership",
            user_message="You don't have access to this organization.",
        )

    return membership


async def get_current_user(
    request: Request,
    db: DbDep,
    authorization: Annotated[str | None, Header()] = None,
    x_organization_id: Annotated[str | None, Header()] = None,
) -> CurrentUser:
    """Authenticate, then bind the request to one organization.

    ``X-Organization-Id`` lets a multi-org user switch context without logging
    in again, but it is only ever a *request*: it is honoured solely when the
    database confirms an active membership. No code path grants access on the
    strength of a header alone.
    """
    if not authorization or not authorization.lower().startswith("bearer "):
        raise AuthenticationError("missing bearer token")

    # decode_token returns a TokenPayload dataclass (not a raw dict), and
    # already raises AuthenticationError on an expired/invalid/wrong-type
    # token - see app.auth.security.decode_token.
    payload = decode_token(authorization.split(" ", 1)[1].strip(), expected_type="access")
    user_id = payload.user_id

    user = await db.get(User, user_id)
    if user is None or not user.is_active:
        raise AuthenticationError("user not found or disabled")

    # A bumped token_version (password change / "log out everywhere") must
    # invalidate every token issued before it, even if it hasn't expired yet.
    if payload.token_version != user.token_version:
        raise AuthenticationError("token has been revoked")

    requested_business_id: uuid.UUID | None = None
    if x_organization_id:
        try:
            requested_business_id = uuid.UUID(x_organization_id)
        except ValueError:
            raise AuthorizationError(
                "malformed organization id",
                user_message="We couldn't switch organizations. Please try again.",
            ) from None
    elif payload.business_id:
        requested_business_id = payload.business_id

    if requested_business_id is None:
        raise AuthorizationError(
            "no organization selected",
            user_message="Please select an organization to continue.",
        )

    membership = await _resolve_membership(
        db, user_id=user_id, business_id=requested_business_id
    )
    role = OrgRole(membership.role)

    principal = CurrentUser(
        user_id=user_id,
        user=user,
        business_id=membership.business_id,
        business=membership.business,
        membership_id=membership.id,
        role=role,
        team_id=membership.team_id,
        permissions=effective_permissions(
            role,
            granted=membership.granted_permissions,
            revoked=membership.revoked_permissions,
        ),
    )

    # Handy for audit rows and structured logs downstream.
    request.state.business_id = str(principal.business_id)
    request.state.user_id = str(principal.user_id)
    return principal


CurrentUserDep = Annotated[CurrentUser, Depends(get_current_user)]


def requires(*permissions: Permission | str):
    """Dependency factory gating an endpoint on one or more permissions.

        @router.get("/customers")
        async def list_customers(
            db: DbDep,
            principal: Annotated[CurrentUser, requires("customer:read")],
        ): ...

    Passing the check means the user may call the endpoint. It says nothing
    about which rows come back - that is always the scope filter's job.
    """

    async def dependency(db: DbDep, principal: CurrentUserDep) -> CurrentUser:
        for permission in permissions:
            principal.require(permission)
        await principal.load_visibility(db)
        return principal

    return Depends(dependency)