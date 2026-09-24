from __future__ import annotations

import uuid
from typing import Any

from app.models.audit import AuditLog
from app.repositories.base import TenantRepository


class AuditRepository(TenantRepository[AuditLog]):
    model = AuditLog

    async def record(
        self,
        *,
        action: str,
        actor_user_id: uuid.UUID | None,
        entity_type: str | None = None,
        entity_id: uuid.UUID | None = None,
        result: str = "success",
        request_id: str | None = None,
        ip_address: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> AuditLog:
        entry = AuditLog(
            business_id=self.business_id,
            actor_user_id=actor_user_id,
            action=action,
            entity_type=entity_type,
            entity_id=entity_id,
            result=result,
            request_id=request_id,
            ip_address=ip_address,
            metadata_json=metadata or {},
        )
        self.session.add(entry)
        return entry
