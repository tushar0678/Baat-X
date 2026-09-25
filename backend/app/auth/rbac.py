"""Role capabilities and the three-tier visibility scope.

Replaces the old binary ``can_read_all``, which only answered "everything or
just mine" - leaving no room for a team lead and, worse, leaving several
endpoints with no row filter at all.

Two separate questions, kept apart on purpose:

    can(...)              may this user perform this action?
    scope_filter(...)     which rows may they see?

A salesperson and a manager may both hold ``lead:read``; what differs is scope.
Conflating the two is how a CRM leaks between teams.

Roles are keyed by their string value, so this works with the legacy per-user
``Role`` and the per-membership ``OrgRole`` alike - both spell "owner" the same
way, so no call site has to know which enum it is holding.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from enum import StrEnum


class VisibilityScope(StrEnum):
    OWN = "own"
    TEAM = "team"
    ORG = "org"


# Keyed by the enum's *value*, so Role.OWNER and OrgRole.OWNER both land here.
ROLE_SCOPE: dict[str, VisibilityScope] = {
    "owner": VisibilityScope.ORG,
    "admin": VisibilityScope.ORG,       # legacy Role.ADMIN
    "manager": VisibilityScope.ORG,
    "team_lead": VisibilityScope.TEAM,
    "member": VisibilityScope.OWN,
    "salesperson": VisibilityScope.OWN,  # legacy Role.SALESPERSON
    "viewer": VisibilityScope.OWN,
}


def visibility_scope(role) -> VisibilityScope:  # noqa: ANN001 - Role | OrgRole | str
    """Unknown roles fall to OWN, so a bad value under-shares, never over-shares."""
    return ROLE_SCOPE.get(str(getattr(role, "value", role)), VisibilityScope.OWN)


def can_read_all(role) -> bool:  # noqa: ANN001
    """Kept for call sites not yet migrated. Prefer ``scope_filter``."""
    return visibility_scope(role) is VisibilityScope.ORG


@dataclass(slots=True)
class ScopeFilter:
    """What one request may see, in a form repositories can apply directly.

    ``user_ids is None`` means "no row restriction" (organization scope).
    Anything else is the exact set of owners whose rows are visible, which a
    repository can drop straight into ``.in_(...)``.
    """

    scope: VisibilityScope
    user_id: uuid.UUID
    user_ids: set[uuid.UUID] | None = None
    team_ids: set[uuid.UUID] = field(default_factory=set)

    @property
    def unrestricted(self) -> bool:
        return self.scope is VisibilityScope.ORG

    def owns(self, *owner_ids: uuid.UUID | None) -> bool:
        """True when any of the given owner ids falls inside this scope."""
        if self.unrestricted:
            return True
        allowed = self.user_ids if self.user_ids is not None else {self.user_id}
        return any(owner in allowed for owner in owner_ids if owner is not None)

    def allows(self, record) -> bool:  # noqa: ANN001
        """Ownership check for a row already loaded by primary key.

        Note ``assigned_user_id`` - that is the Lead/FollowUp spelling in this
        codebase; getting it wrong would silently disable the filter.

        A row with no owner at all (legacy data, or an org-level record) stays
        visible: hiding it would strand data nobody could ever reach.
        """
        if self.unrestricted:
            return True

        owners = [
            getattr(record, name, None)
            for name in ("owner_user_id", "assigned_user_id", "created_by_user_id")
        ]
        if not any(owners):
            return True

        if self.owns(*owners):
            return True

        record_team = getattr(record, "team_id", None)
        return record_team is not None and record_team in self.team_ids


def scope_filter(
    role,  # noqa: ANN001 - Role | OrgRole | str
    user_id: uuid.UUID,
    *,
    team_ids: set[uuid.UUID] | None = None,
    teammate_user_ids: set[uuid.UUID] | None = None,
) -> ScopeFilter:
    """Build the filter for a principal.

    A team lead sees their own rows plus their teammates'. Until teams are
    populated, ``teammate_user_ids`` is empty and a lead behaves exactly like a
    member - the safe direction to fail in.
    """
    scope = visibility_scope(role)

    if scope is VisibilityScope.ORG:
        user_ids = None
    elif scope is VisibilityScope.TEAM:
        user_ids = set(teammate_user_ids or set()) | {user_id}
    else:
        user_ids = {user_id}

    return ScopeFilter(
        scope=scope,
        user_id=user_id,
        user_ids=user_ids,
        team_ids=set(team_ids or set()),
    )
