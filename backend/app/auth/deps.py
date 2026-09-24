"""FastAPI dependencies: authenticated principal + tenant context."""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import Annotated

from fastapi import Depends, Header, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.rbac import Permission, require_permission
from app.auth.security import decode_token
from app.core.errors import AuthenticationError, PermissionError_
from app.db.session import get_db
from app.models.enums import Role
from app.models.tenancy import Business, BusinessMembership, User

bearer_scheme = HTTPBearer(auto_error=False)


@dataclass(slots=True)
class CurrentUser:
    """Everything downstream code needs; business_id is never optional here."""

    user: User
    business: Business
    business_id: uuid.UUID
    role: Role

    @property
    def user_id(self) -> uuid.UUID:
        return self.user.id

    def require(self, permission: Permission) -> None:
        require_permission(self.role, permission)


async def get_current_user(
    request: Request,
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer_scheme)],
    db: Annotated[AsyncSession, Depends(get_db)],
    x_business_id: Annotated[str | None, Header(alias="X-Business-Id")] = None,
) -> CurrentUser:
    if credentials is None or not credentials.credentials:
        raise AuthenticationError("missing bearer token")

    payload = decode_token(credentials.credentials, "access")

    user = await db.get(User, payload.user_id)
    if user is None or not user.is_active:
        raise AuthenticationError("user not found or inactive")
    if user.token_version != payload.token_version:
        raise AuthenticationError(
            "token revoked",
            user_message="Your session is no longer valid. Please sign in again.",
        )

    # The business may be switched per-request, but only to one the user belongs to.
    target_business_id = payload.business_id
    if x_business_id:
        try:
            target_business_id = uuid.UUID(x_business_id)
        except ValueError as exc:
            raise AuthenticationError("invalid X-Business-Id header") from exc
    if target_business_id is None:
        raise AuthenticationError(
            "no business context", user_message="Please select or create a business first."
        )

    membership = (
        await db.execute(
            select(BusinessMembership).where(
                BusinessMembership.user_id == user.id,
                BusinessMembership.business_id == target_business_id,
                BusinessMembership.is_active.is_(True),
            )
        )
    ).scalar_one_or_none()
    if membership is None:
        raise PermissionError_("no active membership for business")

    business = await db.get(Business, target_business_id)
    if business is None or not business.is_active:
        raise PermissionError_("business inactive")

    principal = CurrentUser(
        user=user, business=business, business_id=business.id, role=Role(membership.role)
    )
    # Used by the audit middleware; contains identifiers only.
    request.state.principal = principal
    return principal


CurrentUserDep = Annotated[CurrentUser, Depends(get_current_user)]
DbDep = Annotated[AsyncSession, Depends(get_db)]


def requires(permission: Permission):  # noqa: ANN201 - FastAPI dependency factory
    async def _dep(principal: CurrentUserDep) -> CurrentUser:
        principal.require(permission)
        return principal

    return Depends(_dep)
