"""Role-based access control.

OWNER      - everything, including billing and deleting the business.
ADMIN      - CRM, team, reports, settings.
SALESPERSON- own/assigned customers, leads and follow-ups only.
"""

from __future__ import annotations

from app.core.errors import PermissionError_
from app.models.enums import Role

Permission = str

PERMISSIONS: dict[Role, set[Permission]] = {
    Role.OWNER: {
        "customer:read", "customer:read_all", "customer:write", "customer:delete",
        "lead:read", "lead:read_all", "lead:write", "lead:convert",
        "followup:read", "followup:read_all", "followup:write",
        "ai:process", "assistant:query",
        "report:read", "report:read_all",
        "whatsapp:draft", "whatsapp:send",
        "team:read", "team:write", "business:write",
        "billing:read", "billing:write", "audit:read",
    },
    Role.ADMIN: {
        "customer:read", "customer:read_all", "customer:write", "customer:delete",
        "lead:read", "lead:read_all", "lead:write", "lead:convert",
        "followup:read", "followup:read_all", "followup:write",
        "ai:process", "assistant:query",
        "report:read", "report:read_all",
        "whatsapp:draft", "whatsapp:send",
        "team:read", "team:write", "business:write",
        "billing:read", "audit:read",
    },
    Role.SALESPERSON: {
        "customer:read", "customer:write",
        "lead:read", "lead:write", "lead:convert",
        "followup:read", "followup:write",
        "ai:process", "assistant:query",
        "report:read",
        "whatsapp:draft", "whatsapp:send",
        "team:read",
    },
}


def has_permission(role: Role, permission: Permission) -> bool:
    return permission in PERMISSIONS.get(role, set())


def require_permission(role: Role, permission: Permission) -> None:
    if not has_permission(role, permission):
        raise PermissionError_(
            f"role {role} lacks {permission}", details={"required_permission": permission}
        )


def can_read_all(role: Role) -> bool:
    """Salespeople are scoped to records they own/are assigned."""
    return has_permission(role, "customer:read_all")
