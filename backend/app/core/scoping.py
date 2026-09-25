"""Row-level visibility. This is where data isolation is actually won.

Permissions answer *may this user read customers at all?*. This module answers
the harder question: *which customer rows?* Every list, search, report, export
and assistant query funnels through :func:`scope_query`, so there is exactly
one place to audit and exactly one place to get right.

Three scopes, widest wins:

    org   - every row in the organization       (manager, owner)
    team  - rows owned by the user's team tree  (team lead)
    own   - rows the user owns or is assigned   (salesperson, broker, agent)

The tenant filter is *not* one of the three. ``business_id`` is applied
unconditionally, on top of the scope, on every query - a bug in scope
resolution can at worst widen access inside one organization, never across
organizations.
"""

from __future__ import annotations

import uuid
from enum import StrEnum
from typing import Any, TypeVar

from sqlalchemy import Select, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.permissions import Permission
from app.models.tenancy import Team

T = TypeVar("T")

# Ownership columns, in the order they appear across BaatX models. Note
# ``assigned_user_id`` - that is the Lead/FollowUp spelling in this codebase.
OWNER_COLUMNS = ("owner_user_id", "assigned_user_id", "created_by_user_id")


class VisibilityScope(StrEnum):
    OWN = "own"
    TEAM = "team"
    ORG = "org"


def resolve_scope(permissions: frozenset[Permission]) -> VisibilityScope:
    """Widest granted scope. Absent any grant, a user sees only their own rows."""
    if Permission.VIEW_ORG_DATA in permissions:
        return VisibilityScope.ORG
    if Permission.VIEW_TEAM_DATA in permissions:
        return VisibilityScope.TEAM
    return VisibilityScope.OWN


async def visible_team_ids(
    session: AsyncSession,
    *,
    business_id: uuid.UUID,
    root_team_id: uuid.UUID | None,
) -> set[uuid.UUID]:
    """The user's team plus every team nested beneath it.

    Walks breadth-first with a visited set, so a cycle introduced by bad data
    cannot hang the request. Constrained to one ``business_id``, so a
    mis-parented team elsewhere can never pull foreign teams into scope.
    """
    if root_team_id is None:
        return set()

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


async def visible_user_ids(
    session: AsyncSession,
    *,
    business_id: uuid.UUID,
    team_ids: set[uuid.UUID],
) -> set[uuid.UUID]:
    """Active members of the given teams, within this organization only."""
    if not team_ids:
        return set()

    from app.models.tenancy import BusinessMembership  # local: avoids a cycle

    result = await session.execute(
        select(BusinessMembership.user_id).where(
            BusinessMembership.business_id == business_id,
            BusinessMembership.team_id.in_(team_ids),
            BusinessMembership.is_active.is_(True),
        )
    )
    return {row[0] for row in result.all()}


def scope_query(
    stmt: Select[Any],
    model: type[T],
    *,
    business_id: uuid.UUID,
    scope: VisibilityScope,
    user_id: uuid.UUID,
    team_ids: set[uuid.UUID] | None = None,
    teammate_user_ids: set[uuid.UUID] | None = None,
) -> Select[Any]:
    """Apply tenant + visibility filters to a CRM query.

    Call this before executing any query that returns CRM rows:

        stmt = scope_query(select(Customer), Customer, **ctx.scope_kwargs())

    ``model`` is inspected for whichever ownership columns it happens to have,
    so this works unchanged across Customer, Lead, FollowUp and
    ConversationEvent without a bespoke branch for each.
    """
    # Tenant boundary. Unconditional, and first.
    stmt = stmt.where(model.business_id == business_id)  # type: ignore[attr-defined]

    if scope is VisibilityScope.ORG:
        return stmt

    owner_columns = [
        getattr(model, name) for name in OWNER_COLUMNS if hasattr(model, name)
    ]
    team_column = getattr(model, "team_id", None)

    if not owner_columns and team_column is None:
        # A tenant table with no ownership concept (e.g. org-wide settings).
        # Narrowing further is impossible, so tenant isolation stands alone
        # rather than silently returning nothing.
        return stmt

    if scope is VisibilityScope.TEAM:
        allowed_users = set(teammate_user_ids or set()) | {user_id}
        clauses = [column.in_(allowed_users) for column in owner_columns]
        if team_column is not None and team_ids:
            clauses.append(team_column.in_(team_ids))
        return stmt.where(or_(*clauses))

    # OWN
    return stmt.where(or_(*[column == user_id for column in owner_columns]))


def can_access_record(
    record: Any,
    *,
    business_id: uuid.UUID,
    scope: VisibilityScope,
    user_id: uuid.UUID,
    team_ids: set[uuid.UUID] | None = None,
    teammate_user_ids: set[uuid.UUID] | None = None,
) -> bool:
    """Same rules as :func:`scope_query`, for a row already loaded by id.

    Used by detail/update/delete endpoints, which fetch by primary key and so
    never pass through the scoped query path.
    """
    if getattr(record, "business_id", None) != business_id:
        return False

    if scope is VisibilityScope.ORG:
        return True

    owners = {
        getattr(record, name)
        for name in OWNER_COLUMNS
        if getattr(record, name, None) is not None
    }
    record_team = getattr(record, "team_id", None)

    # A row with no owner at all (legacy data) stays visible: hiding it would
    # strand data nobody could ever reach.
    if not owners and record_team is None:
        return True

    if scope is VisibilityScope.TEAM:
        allowed_users = set(teammate_user_ids or set()) | {user_id}
        if owners & allowed_users:
            return True
        return record_team is not None and record_team in (team_ids or set())

    return user_id in owners
