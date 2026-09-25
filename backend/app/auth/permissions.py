"""The permission catalogue and what each role gets by default.

Roles are a convenience, not the authorization model. Every check asks for a
*permission*; roles merely seed a default set that a manager can extend or trim
per member.

Two axes, deliberately separate:

  capability  - may this user create/edit/delete/export at all?
  scope       - which rows may they see? (own / team / organization)

A salesperson and a manager may both hold ``customer:read``; what differs is
their scope. Conflating the two is how CRMs leak between teams.
"""

from __future__ import annotations

from enum import StrEnum

from app.models.enums import OrgRole


class Permission(StrEnum):
    # --- visibility scope (highest granted one wins) ---
    VIEW_OWN_DATA = "view:own"
    VIEW_TEAM_DATA = "view:team"
    VIEW_ORG_DATA = "view:org"

    # --- customers ---
    CUSTOMER_READ = "customer:read"
    CUSTOMER_WRITE = "customer:write"
    CUSTOMER_DELETE = "customer:delete"
    CUSTOMER_ASSIGN = "customer:assign"

    # --- leads ---
    LEAD_READ = "lead:read"
    LEAD_WRITE = "lead:write"
    LEAD_DELETE = "lead:delete"
    LEAD_ASSIGN = "lead:assign"
    LEAD_CONVERT = "lead:convert"

    # --- conversations, calls, AI ---
    AI_PROCESS = "ai:process"
    CALL_READ = "call:read"
    CONVERSATION_READ = "conversation:read"
    ASSISTANT_QUERY = "assistant:query"

    # --- follow-ups ---
    FOLLOWUP_READ = "followup:read"
    FOLLOWUP_WRITE = "followup:write"
    FOLLOWUP_ASSIGN = "followup:assign"

    # --- messaging ---
    WHATSAPP_DRAFT = "whatsapp:draft"
    WHATSAPP_SEND = "whatsapp:send"

    # --- reporting ---
    REPORT_READ = "report:read"
    REPORT_EXPORT = "report:export"

    # --- administration ---
    TEAM_MANAGE = "team:manage"
    USER_MANAGE = "user:manage"
    PERMISSION_MANAGE = "permission:manage"
    ORG_MANAGE = "org:manage"
    AUDIT_VIEW = "audit:view"


_MEMBER: frozenset[Permission] = frozenset({
    Permission.VIEW_OWN_DATA,
    Permission.CUSTOMER_READ,
    Permission.CUSTOMER_WRITE,
    Permission.LEAD_READ,
    Permission.LEAD_WRITE,
    Permission.LEAD_CONVERT,
    Permission.AI_PROCESS,
    Permission.CALL_READ,
    Permission.CONVERSATION_READ,
    Permission.ASSISTANT_QUERY,
    Permission.FOLLOWUP_READ,
    Permission.FOLLOWUP_WRITE,
    Permission.WHATSAPP_DRAFT,
    Permission.WHATSAPP_SEND,
    Permission.REPORT_READ,
})

_TEAM_LEAD: frozenset[Permission] = _MEMBER | {
    Permission.VIEW_TEAM_DATA,
    Permission.CUSTOMER_ASSIGN,
    Permission.LEAD_ASSIGN,
    Permission.FOLLOWUP_ASSIGN,
    Permission.CUSTOMER_DELETE,
    Permission.LEAD_DELETE,
}

_MANAGER: frozenset[Permission] = _TEAM_LEAD | {
    Permission.VIEW_ORG_DATA,
    Permission.TEAM_MANAGE,
    Permission.USER_MANAGE,
    Permission.REPORT_EXPORT,
    Permission.AUDIT_VIEW,
}

_OWNER: frozenset[Permission] = _MANAGER | {
    Permission.ORG_MANAGE,
    Permission.PERMISSION_MANAGE,
}

# Read-only: an auditor or a silent stakeholder.
_VIEWER: frozenset[Permission] = frozenset({
    Permission.VIEW_OWN_DATA,
    Permission.CUSTOMER_READ,
    Permission.LEAD_READ,
    Permission.CALL_READ,
    Permission.CONVERSATION_READ,
    Permission.FOLLOWUP_READ,
    Permission.REPORT_READ,
})

ROLE_PERMISSIONS: dict[OrgRole, frozenset[Permission]] = {
    OrgRole.OWNER: _OWNER,
    OrgRole.MANAGER: _MANAGER,
    OrgRole.TEAM_LEAD: _TEAM_LEAD,
    OrgRole.MEMBER: _MEMBER,
    OrgRole.VIEWER: _VIEWER,
}


def effective_permissions(
    role: OrgRole,
    granted: list[str] | None = None,
    revoked: list[str] | None = None,
) -> frozenset[Permission]:
    """Role defaults, plus per-member grants, minus per-member revocations.

    Revocation is applied last and always wins, so an explicit "this person
    must not export" cannot be undone by a later grant. Unknown permission
    strings are ignored rather than raising - a typo in stored data must never
    widen access, and must never lock a user out.
    """
    permissions = set(ROLE_PERMISSIONS.get(role, _VIEWER))

    for name in granted or []:
        try:
            permissions.add(Permission(name))
        except ValueError:
            continue

    for name in revoked or []:
        try:
            permissions.discard(Permission(name))
        except ValueError:
            continue

    return frozenset(permissions)
